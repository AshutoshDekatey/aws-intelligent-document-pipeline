"""EventBridge processing tasks. AWS clients are created only on invocation."""
import hashlib
import json
import logging
import os
import time
from pathlib import PurePosixPath

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ConnectionError, ReadTimeoutError
from pydantic import ValidationError

from app import PROMPT, parse_extraction
from finance import validate_invoice

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
PROMPT_VERSION = 'invoice-extraction/2'
EXTRACTION_PROMPT = PROMPT + """
Copy printed monetary values exactly, including inconsistent amounts.
Do not recalculate, fix, infer, or round any values. Use ISO dates only for
unambiguous printed dates. Skip headers. There can be at most 30 lines.
A receipt number/date can fill the invoice number/date fields if explicitly labeled.
"""
MAX_IMAGE = 5_000_000
MAX_TEXT = 12_000
LEASE_SECONDS = 900  # Exceeds the workflow timeout plus a final Lambda invocation.
FORMATS = {'.txt': {'text/plain', 'application/octet-stream'},
           '.png': {'image/png', 'application/octet-stream'},
           '.jpg': {'image/jpeg', 'application/octet-stream'},
           '.jpeg': {'image/jpeg', 'application/octet-stream'}}
TRANSIENT = {'Throttling', 'ThrottlingException', 'TooManyRequestsException',
             'ServiceUnavailable', 'ServiceUnavailableException', 'InternalServerError',
             'InternalServerException', 'InternalServerErrorException', 'SlowDown',
             'ModelNotReadyException', 'ModelTimeoutException', 'RequestTimeout',
             'ProvisionedThroughputExceededException', 'RequestLimitExceeded',
             'TransactionConflictException', 'ConditionalRequestConflict'}


class RetryableFailure(RuntimeError):
    pass


class PermanentFailure(ValueError):
    pass


def emit(state, event, **fields):
    LOG.info(json.dumps({'event': event, 'execution_id': state['execution_id'],
                         'document_id': state.get('document', {}).get('document_id'), **fields}))


def source_from(event, input_bucket):
    try:
        detail = event['detail']
        obj = detail['object']
        bucket, key, version = detail['bucket']['name'], obj['key'], obj['version-id']
        if (event['source'] != 'aws.s3' or event['detail-type'] != 'Object Created'
                or bucket != input_bucket or not isinstance(key, str)
                or not key.startswith('incoming/') or not isinstance(version, str)
                or not version or version == 'null'):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise PermanentFailure('INVALID_EVENT') from None
    return {'bucket': bucket, 'key': key, 'version_id': version}


def s3_args(source):
    return {'Bucket': source['bucket'], 'Key': source['key'], 'VersionId': source['version_id']}


def read_document(s3, source):
    suffix = PurePosixPath(source['key']).suffix.lower()
    if suffix not in FORMATS:
        raise PermanentFailure('UNSUPPORTED_FORMAT')
    limit = MAX_TEXT if suffix == '.txt' else MAX_IMAGE
    response = s3.get_object(**s3_args(source))
    body = response['Body']
    try:
        size = response['ContentLength']
        mime = response.get('ContentType', '').split(';')[0].strip().lower()
        if not 0 < size <= limit:
            raise PermanentFailure('INVALID_SIZE')
        if mime not in FORMATS[suffix] or response.get('ContentEncoding'):
            raise PermanentFailure('INVALID_METADATA')
        raw = body.read(limit + 1)
        if len(raw) != size:
            raise RetryableFailure('INCOMPLETE_S3_READ')
    finally:
        body.close()
    if suffix == '.txt':
        plain_text(raw)
    elif suffix == '.png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise PermanentFailure('INVALID_IMAGE_SIGNATURE')
    elif suffix in {'.jpg', '.jpeg'} and not raw.startswith(b'\xff\xd8\xff'):
        raise PermanentFailure('INVALID_IMAGE_SIGNATURE')
    return raw, suffix


def plain_text(raw):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise PermanentFailure('INVALID_UTF8') from None
    if not text.strip() or any(ord(ch) < 32 and ch not in '\t\r\n' for ch in text):
        raise PermanentFailure('INVALID_TEXT')
    return text


def inspect(state, s3, input_bucket):
    source = source_from(state['event'], input_bucket)
    raw, _ = read_document(s3, source)
    return {'source': source, 'document_id': hashlib.sha256(raw).hexdigest()}


def conditional_failure(exc):
    return exc.response['Error']['Code'] == 'ConditionalCheckFailedException'


def lookup(table, doc_id):
    return table.get_item(Key={'document_id': doc_id}, ConsistentRead=True).get('Item')


def claim(state, table, now):
    doc = state['document']
    doc_id = doc['document_id']
    owner = state['execution_id']
    key = {'document_id': doc_id}
    lease = now + LEASE_SECONDS
    try:
        table.put_item(Item={**key, 'source': doc['source'], 'owner': owner,
                             'status': 'PROCESSING', 'lease_until': lease, 'updated_at': now},
                       ConditionExpression='attribute_not_exists(document_id)')
        return {'outcome': 'CLAIMED'}
    except ClientError as exc:
        if not conditional_failure(exc):
            raise
    row = lookup(table, doc_id)
    if not row:
        raise RetryableFailure('CLAIM_RACE')
    if row['status'] == 'ACCEPTED':
        return {'outcome': 'DUPLICATE_ACCEPTED'}
    if row['owner'] == owner and row['status'] in {'PROCESSING', 'READY'}:
        return {'outcome': 'CLAIMED'}
    if state['event'].get('reprocess') is True and row['source'] == doc['source']:
        try:
            table.update_item(
                Key=key, UpdateExpression='SET #s=:working, #o=:owner, lease_until=:lease, updated_at=:now',
                ConditionExpression='#o=:prior AND (#s=:review OR ((#s=:working OR #s=:ready) AND lease_until <= :now))',
                ExpressionAttributeNames={'#s': 'status', '#o': 'owner'},
                ExpressionAttributeValues={':working': 'PROCESSING', ':ready': 'READY',
                                           ':review': 'REVIEW_REQUIRED', ':owner': owner,
                                           ':prior': row['owner'], ':lease': lease, ':now': now})
            return {'outcome': 'CLAIMED'}
        except ClientError as exc:
            if not conditional_failure(exc):
                raise
            raise RetryableFailure('CLAIM_RACE') from None
    outcome = 'DUPLICATE_REVIEW' if row['status'] == 'REVIEW_REQUIRED' else 'DUPLICATE_IN_PROGRESS'
    return {'outcome': outcome}


def extract_invoice(state, s3, textract, bedrock, table, model, demo, retry, now):
    doc_id = state['document']['document_id']
    source = state['document']['source']
    row = lookup(table, doc_id)
    if not row or row['owner'] != state['execution_id'] or row['status'] not in {'PROCESSING', 'READY'}:
        raise PermanentFailure('CLAIM_LOST')
    candidate = row.get('candidate')
    if candidate is None:
        filename = PurePosixPath(source['key']).name
        if demo and (filename == 'exhausted.txt' or (filename == 'recoverable.txt' and retry == 0)):
            emit(state, 'injected_transient', retry=retry)
            raise RetryableFailure('INJECTED_TRANSIENT')
        raw, suffix = read_document(s3, source)
        if hashlib.sha256(raw).hexdigest() != doc_id:
            raise PermanentFailure('SOURCE_DIGEST_MISMATCH')
        if suffix == '.txt':
            text = plain_text(raw)
        else:
            response = textract.detect_document_text(Document={'Bytes': raw})
            emit(state, 'textract_completed', api='DetectDocumentText',
                 request_id=response.get('ResponseMetadata', {}).get('RequestId'))
            text = '\n'.join(block['Text'] for block in response['Blocks'] if block['BlockType'] == 'LINE')
            if not text.strip() or len(text.encode()) > MAX_TEXT:
                raise PermanentFailure('INVALID_OCR_TEXT')
        response = bedrock.converse(
            modelId=model, system=[{'text': EXTRACTION_PROMPT}],
            messages=[{'role': 'user', 'content': [{'text': 'Document:\n' + text}]}],
            inferenceConfig={'maxTokens': 1800, 'temperature': 0},
        )
        emit(state, 'bedrock_completed', api='Converse', model_id=model, prompt_version=PROMPT_VERSION,
             request_id=response.get('ResponseMetadata', {}).get('RequestId'), usage=response.get('usage', {}))
        try:
            invoice = validate_invoice(parse_extraction(response))
        except (ValidationError, ValueError, KeyError, TypeError):
            raise PermanentFailure('INVALID_EXTRACTION') from None
        candidate = json.dumps({'schema_version': '0.2', 'document_id': doc_id, 'source': source,
                                'execution_id': state['execution_id'], 'model_id': model,
                                'prompt_version': PROMPT_VERSION, 'invoice': invoice})
    table.update_item(
        Key={'document_id': doc_id}, UpdateExpression='SET #s=:ready, candidate=:candidate, updated_at=:now',
        ConditionExpression='#o=:owner AND (#s=:working OR #s=:ready)',
        ExpressionAttributeNames={'#s': 'status', '#o': 'owner'},
        ExpressionAttributeValues={':ready': 'READY', ':working': 'PROCESSING', ':candidate': candidate,
                                   ':owner': state['execution_id'], ':now': now})


def publish(state, s3, table, output_bucket, now):
    doc_id = state['document']['document_id']
    row = lookup(table, doc_id)
    if not row or row['owner'] != state['execution_id'] or row['status'] not in {'READY', 'ACCEPTED'}:
        raise PermanentFailure('CLAIM_LOST')
    key = f'validated/{doc_id}.json'
    if row['status'] == 'READY':
        try:
            s3.put_object(Bucket=output_bucket, Key=key, Body=row['candidate'].encode(),
                          ContentType='application/json', IfNoneMatch='*',
                          Metadata={'document-id': doc_id, 'candidate-sha256': hashlib.sha256(row['candidate'].encode()).hexdigest()})
        except ClientError as exc:
            if exc.response['Error']['Code'] not in {'PreconditionFailed', '412'}:
                raise
            existing = s3.head_object(Bucket=output_bucket, Key=key)
            if existing['Metadata'].get('candidate-sha256') != hashlib.sha256(row['candidate'].encode()).hexdigest():
                raise PermanentFailure('PUBLISHED_OBJECT_CONFLICT') from None
        try:
            table.update_item(
                Key={'document_id': doc_id},
                UpdateExpression='SET #s=:accepted, output_key=:key, updated_at=:now REMOVE candidate, failure',
                ConditionExpression='#o=:owner AND #s=:ready',
                ExpressionAttributeNames={'#s': 'status', '#o': 'owner'},
                ExpressionAttributeValues={':owner': state['execution_id'], ':ready': 'READY',
                                           ':accepted': 'ACCEPTED', ':key': key, ':now': now})
        except ClientError as exc:
            if not conditional_failure(exc):
                raise
            current = lookup(table, doc_id)
            if not current or current['owner'] != state['execution_id'] or current['status'] != 'ACCEPTED':
                raise PermanentFailure('CLAIM_LOST') from None
    emit(state, 'accepted', output_key=key)
    return {'outcome': 'ACCEPTED', 'output_key': key}


def record_review(state, table, input_bucket, now):
    error = state['failure']['Error']
    classification = 'permanent' if error == 'PermanentFailure' else 'operational'
    source = state.get('document', {}).get('source')
    if not source:
        try:
            source = source_from(state['event'], input_bucket)
        except PermanentFailure:
            source = {}
    if 'claim' in state and state['claim']['outcome'] == 'CLAIMED':
        doc_id = state['document']['document_id']
        try:
            table.update_item(
                Key={'document_id': doc_id},
                UpdateExpression='SET #s=:review, failure=:failure, updated_at=:now',
                ConditionExpression='#o=:owner AND (#s=:working OR #s=:ready OR #s=:review)',
                ExpressionAttributeNames={'#s': 'status', '#o': 'owner'},
                ExpressionAttributeValues={':owner': state['execution_id'], ':ready': 'READY',
                                           ':working': 'PROCESSING', ':review': 'REVIEW_REQUIRED',
                                           ':failure': error, ':now': now})
        except ClientError as exc:
            if not conditional_failure(exc):
                raise
    else:
        # A per-object review record cannot overwrite a different execution's content claim.
        identity = source or {'execution_id': state['execution_id']}
        doc_id = 'review#' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        try:
            table.put_item(Item={'document_id': doc_id, 'status': 'REVIEW_REQUIRED', 'source': source,
                                 'owner': state['execution_id'], 'updated_at': now, 'failure': error},
                           ConditionExpression='attribute_not_exists(document_id)')
        except ClientError as exc:
            if not conditional_failure(exc):
                raise
    emit(state, 'review_required', review_id=doc_id, classification=classification, error=error)
    return {'document_id': doc_id, 'source': source, 'execution_id': state['execution_id'],
            'error': error, 'classification': classification}


def handler(request, _context):
    state, action = request['state'], request['action']
    config = Config(retries={'mode': 'standard', 'total_max_attempts': 1}, connect_timeout=3, read_timeout=40)
    now = int(time.time())
    try:
        if action == 'Inspect':
            return inspect(state, boto3.client('s3', config=config), os.environ['INPUT_BUCKET'])
        table = boto3.resource('dynamodb', config=config).Table(os.environ['DOCUMENTS_TABLE'])
        if action == 'Claim':
            result = claim(state, table, now)
            emit(state, 'claim', outcome=result['outcome'])
            return result
        if action == 'Extract':
            extract_invoice(state, boto3.client('s3', config=config), boto3.client('textract', config=config),
                            boto3.client('bedrock-runtime', config=config), table, os.environ['MODEL_ID'],
                            os.environ['ENABLE_DEMO_FAILURES'] == 'true', request['retry'], now)
            return {'outcome': 'READY'}
        if action == 'Publish':
            return publish(state, boto3.client('s3', config=config), table, os.environ['OUTPUT_BUCKET'], now)
        if action == 'Review':
            return record_review(state, table, os.environ['INPUT_BUCKET'], now)
        raise PermanentFailure('UNKNOWN_ACTION')
    except ClientError as exc:
        code = exc.response['Error']['Code']
        status = exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode', 0)
        emit(state, 'task_error', action=action, code=code)
        if code in TRANSIENT or status >= 500 or status in {408, 429}:
            raise RetryableFailure('AWS_TRANSIENT') from None
        if code in {'BadDocumentException', 'UnsupportedDocumentException', 'DocumentTooLargeException',
                    'NoSuchKey', 'NoSuchVersion', 'InvalidParameterException'}:
            raise PermanentFailure('AWS_DOCUMENT_REJECTED') from None
        raise RuntimeError('AWS_OPERATION_FAILED') from None
    except (ConnectionError, ReadTimeoutError):
        emit(state, 'task_error', action=action, code='NETWORK_TIMEOUT')
        raise RetryableFailure('NETWORK_TIMEOUT') from None
    except (PermanentFailure, RetryableFailure) as exc:
        emit(state, 'task_error', action=action, code=str(exc))
        raise
