import hashlib
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from finance import validate_invoice
from validation import InvalidInvoice
from workflow import (PermanentFailure, RetryableFailure, claim, extract_invoice, inspect,
                      publish, record_review)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples'


def client_error(code):
    return ClientError({'Error': {'Code': code, 'Message': 'private'}}, 'AWS')


def event(key='incoming/a+b c.txt'):
    return {'source': 'aws.s3', 'detail-type': 'Object Created',
            'detail': {'bucket': {'name': 'input'},
                       'object': {'key': key, 'version-id': 'version'}}}


def setup_document(path='invoice.txt', key='incoming/a+b c.txt', mime='text/plain'):
    raw = (EXAMPLES / path).read_bytes()
    s3 = Mock()
    s3.get_object.side_effect = lambda **kw: {
        'ContentType': mime, 'ContentLength': len(raw), 'Body': io.BytesIO(raw)}
    state = {'event': event(key), 'execution_id': 'execution-a'}
    state['document'] = inspect(state, s3, 'input')
    state['claim'] = {'outcome': 'CLAIMED'}
    return state, s3


def invoice():
    return json.loads((EXAMPLES / 'expected.json').read_text())


def response(fields):
    return {'output': {'message': {'content': [{'text': json.dumps(fields)}]}},
            'stopReason': 'end_turn', 'ResponseMetadata': {'RequestId': 'bedrock-id'}}


def test_uses_version_and_native_event_key():
    state, s3 = setup_document()
    assert state['document']['document_id'] == hashlib.sha256((EXAMPLES / 'invoice.txt').read_bytes()).hexdigest()
    s3.get_object.assert_called_once_with(Bucket='input', Key='incoming/a+b c.txt', VersionId='version')


@pytest.mark.parametrize('key,mime,contents,error', [
    ('incoming/x.csv', 'text/csv', b'a', 'UNSUPPORTED_FORMAT'),
    ('incoming/x.txt', 'image/png', b'a', 'INVALID_METADATA'),
    ('incoming/x.txt', 'text/plain', b'\xff', 'INVALID_UTF8'),
    ('incoming/x.png', 'image/png', b'abc', 'INVALID_IMAGE_SIGNATURE'),
    ('incoming/x.txt', 'text/plain', b'x' * 12001, 'INVALID_SIZE'),
])
def test_bad_inputs(key, mime, contents, error):
    s3 = Mock()
    s3.get_object.return_value = {'Body': io.BytesIO(contents), 'ContentType': mime, 'ContentLength': len(contents)}
    with pytest.raises(PermanentFailure, match=error):
        inspect({'event': event(key)}, s3, 'input')


@pytest.mark.parametrize('field,value', [('total', '34.100'), ('tax', '-0'), ('tax', '3e0'),
                                        ('tax', 3.1), ('invoice_number', None)])
def test_strict_schema(field, value):
    fields = invoice()
    fields[field] = value
    with pytest.raises(ValidationError):
        validate_invoice(fields)


def test_inconsistent_total():
    fields = invoice()
    fields['total'] = '34.11'
    with pytest.raises(InvalidInvoice):
        validate_invoice(fields)


@pytest.mark.parametrize('status,expected', [
    ('PROCESSING', 'DUPLICATE_IN_PROGRESS'), ('READY', 'DUPLICATE_IN_PROGRESS'),
    ('ACCEPTED', 'DUPLICATE_ACCEPTED'), ('REVIEW_REQUIRED', 'DUPLICATE_REVIEW')])
def test_competing_execution_cannot_acquire_existing_record(status, expected):
    state, _ = setup_document()
    table = Mock()
    table.put_item.side_effect = client_error('ConditionalCheckFailedException')
    table.get_item.return_value = {'Item': {'status': status, 'owner': 'execution-b'}}
    assert claim(state, table, 100)['outcome'] == expected
    assert table.put_item.call_args.kwargs['ConditionExpression'] == 'attribute_not_exists(document_id)'
    assert table.get_item.call_args.kwargs['ConsistentRead'] is True
    table.update_item.assert_not_called()


def test_recovering_claim_requires_original_source_and_condition():
    state, _ = setup_document()
    state['event']['reprocess'] = True
    table = Mock()
    table.put_item.side_effect = client_error('ConditionalCheckFailedException')
    row = {'status': 'REVIEW_REQUIRED', 'owner': 'old', 'source': state['document']['source']}
    table.get_item.return_value = {'Item': row}
    assert claim(state, table, 100)['outcome'] == 'CLAIMED'
    assert 'lease_until <= :now' in table.update_item.call_args.kwargs['ConditionExpression']
    table.update_item.reset_mock()
    row['source'] = {**row['source'], 'version_id': 'other-version'}
    assert claim(state, table, 100)['outcome'] == 'DUPLICATE_REVIEW'
    table.update_item.assert_not_called()


def test_textract_then_bedrock_and_checkpoint(caplog):
    state, s3 = setup_document('v02/scanned.png', 'incoming/scanned.png', 'image/png')
    table, ocr, bedrock = Mock(), Mock(), Mock()
    table.get_item.return_value = {'Item': {'owner': 'execution-a', 'status': 'PROCESSING'}}
    ocr.detect_document_text.return_value = {'Blocks': [{'BlockType': 'LINE', 'Text': 'synthetic vendor'}],
                                            'ResponseMetadata': {'RequestId': 'textract-id'}}
    bedrock.converse.return_value = response(invoice())
    extract_invoice(state, s3, ocr, bedrock, table, 'model', False, 0, 100)
    assert ocr.detect_document_text.call_args.kwargs['Document']['Bytes'].startswith(b'\x89PNG')
    assert 'synthetic vendor' in bedrock.converse.call_args.kwargs['messages'][0]['content'][0]['text']
    record = json.loads(table.update_item.call_args.kwargs['ExpressionAttributeValues'][':candidate'])
    assert record['invoice']['total'] == '34.10'
    assert 'textract-id' in caplog.text and 'bedrock-id' in caplog.text
    assert 'synthetic vendor' not in caplog.text


def test_injected_failure_then_recovery():
    state, s3 = setup_document('v02/recoverable.txt', 'incoming/recoverable.txt')
    ocr, bedrock, table = Mock(), Mock(), Mock()
    table.get_item.return_value = {'Item': {'owner': 'execution-a', 'status': 'PROCESSING'}}
    bedrock.converse.return_value = response(invoice())
    with pytest.raises(RetryableFailure, match='INJECTED_TRANSIENT'):
        extract_invoice(state, s3, ocr, bedrock, table, 'model', True, 0, 100)
    bedrock.converse.assert_not_called()
    extract_invoice(state, s3, ocr, bedrock, table, 'model', True, 1, 103)
    bedrock.converse.assert_called_once()


def test_checkpoint_reconcile_preserves_the_same_output():
    state, s3 = setup_document()
    table = Mock()
    candidate = '{"validated":"data"}'
    row = {'owner': 'execution-a', 'status': 'READY', 'candidate': candidate}
    table.get_item.return_value = {'Item': row}
    s3.put_object.side_effect = client_error('PreconditionFailed')
    s3.head_object.return_value = {'Metadata': {'candidate-sha256': hashlib.sha256(candidate.encode()).hexdigest()}}
    assert publish(state, s3, table, 'output', 100)['outcome'] == 'ACCEPTED'
    assert s3.put_object.call_args.kwargs['IfNoneMatch'] == '*'
    assert table.update_item.call_args.kwargs['ExpressionAttributeValues'][':accepted'] == 'ACCEPTED'
    s3.head_object.return_value = {'Metadata': {'candidate-sha256': 'unexpected'}}
    table.update_item.reset_mock()
    with pytest.raises(PermanentFailure, match='PUBLISHED_OBJECT_CONFLICT'):
        publish(state, s3, table, 'output', 101)
    table.update_item.assert_not_called()


def test_review_does_not_mutate_unclaimed_content():
    state = {'event': event(), 'execution_id': 'execution-a', 'failure': {'Error': 'PermanentFailure'}}
    table = Mock()
    result = record_review(state, table, 'input', 100)
    assert result['document_id'].startswith('review#')
    assert result['classification'] == 'permanent'
    table.update_item.assert_not_called()


def test_workflow_definition_and_routing():
    definition = json.loads((ROOT / 'statemachine/pipeline.asl.json').read_text())
    states = definition['States']
    for state in states.values():
        if 'Next' in state:
            assert state['Next'] in states
        for catcher in state.get('Catch', []):
            assert catcher['Next'] in states
    assert states['ExtractAndValidate']['Retry'][0]['MaxAttempts'] == 2
    assert 'PermanentFailure' not in states['ExtractAndValidate']['Retry'][0]['ErrorEquals']
    assert states['NotifyReview']['Next'] == 'NeedsReview'
    assert states['RouteClaim']['Default'] == 'Duplicate'


def test_publish_after_parallel_same_owner_commit():
    state, s3 = setup_document()
    table = Mock()
    table.get_item.side_effect = [
        {'Item': {'owner': 'execution-a', 'status': 'READY', 'candidate': '{}'}},
        {'Item': {'owner': 'execution-a', 'status': 'ACCEPTED'}}
    ]
    table.update_item.side_effect = client_error('ConditionalCheckFailedException')
    assert publish(state, s3, table, 'output', 100)['outcome'] == 'ACCEPTED'


def test_recovery_uses_saved_candidate_without_reinvoking_model():
    state, s3 = setup_document()
    s3.reset_mock()
    table, ocr, bedrock = Mock(), Mock(), Mock()
    table.get_item.return_value = {'Item': {'owner': 'execution-a', 'status': 'PROCESSING',
                                            'candidate': '{"previous":"checkpoint"}'}}
    extract_invoice(state, s3, ocr, bedrock, table, 'model', False, 0, 100)
    s3.get_object.assert_not_called()
    ocr.detect_document_text.assert_not_called()
    bedrock.converse.assert_not_called()
    assert table.update_item.call_args.kwargs['ExpressionAttributeValues'][':candidate'] == '{"previous":"checkpoint"}'
