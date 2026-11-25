"""Run the controlled acceptance suite against the real, deployed AWS stack."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from aws_v02 import add_target, stack_info, target

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples'
EXPECTED = json.loads((EXAMPLES / 'expected.json').read_text())
CASES = {
    'valid': ('invoice.txt', 'text/plain', 'ACCEPTED', 'SYN-2026-001'),
    'duplicate': ('invoice.txt', 'text/plain', 'DUPLICATE_ACCEPTED', None),
    'invalid': ('malformed.txt', 'text/plain', 'ReviewRequired', None),
    'totals': ('v02/inconsistent.txt', 'text/plain', 'ReviewRequired', None),
    'unsupported': ('v02/unsupported.csv', 'text/csv', 'ReviewRequired', None),
    'scan': ('v02/scanned.png', 'image/png', 'ACCEPTED', 'SYN-2026-002'),
    'recovery': ('v02/recoverable.txt', 'text/plain', 'ACCEPTED', 'SYN-2026-003'),
    'exhausted': ('v02/exhausted.txt', 'text/plain', 'ReviewRequired', None),
}
LOG_EVENTS = {
    'valid': {'bedrock_completed', 'accepted'},
    'duplicate': {'claim'},
    'invalid': {'bedrock_completed', 'review_required'},
    'totals': {'bedrock_completed', 'review_required'},
    'unsupported': {'review_required'},
    'scan': {'textract_completed', 'bedrock_completed', 'accepted'},
    'recovery': {'injected_transient', 'bedrock_completed', 'accepted'},
    'exhausted': {'injected_transient', 'review_required'},
}


def pages(client, operation, field, **kwargs):
    for page in client.get_paginator(operation).paginate(**kwargs):
        yield from page.get(field, [])


def poll(check, seconds=300, interval=5):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        value = check()
        if value is not None:
            return value
        time.sleep(interval)
    raise TimeoutError('Evidence did not arrive before the polling deadline')


def find_executions(sfn, outputs, uploads, started):
    found = {}
    running = set()
    for run in pages(sfn, 'list_executions', 'executions', stateMachineArn=outputs['StateMachineArn']):
        if run['startDate'] < started:
            break
        entry = sfn.describe_execution(executionArn=run['executionArn'])
        event = json.loads(entry.get('input', '{}'))
        obj = event.get('detail', {}).get('object', {})
        key = obj.get('key')
        if key not in uploads or obj.get('version-id') != uploads[key]['version']:
            continue
        assert event['source'] == 'aws.s3' and event.get('id'), entry['executionArn']
        if entry['status'] == 'RUNNING':
            running.add(key)
        else:
            found.setdefault(key, []).append(entry)
    return found if not running and found.keys() == uploads.keys() else None


def match_invoice(invoice, number):
    expected = {**EXPECTED, 'invoice_number': number}
    # Numeric quantities are semantically equivalent across decimal formatting.
    for item in invoice['line_items']:
        item['quantity'] = str(Decimal(item['quantity']).normalize())
    assert invoice == expected, f'Extracted JSON differs from expected fields for {number}'


def traces(logs, group, started, execution_id, required):
    found = []
    for event in pages(logs, 'filter_log_events', 'events', logGroupName=group,
                       startTime=int(started.timestamp() * 1000), filterPattern=f'"{execution_id}"'):
        try:
            line = json.loads(event['message'][event['message'].index('{'):])
        except ValueError:
            continue
        if line.get('execution_id') == execution_id:
            found.append(line)
    return found if required <= {line['event'] for line in found} else None


def messages(sqs, queue, expected):
    found = {}

    def check():
        for message in sqs.receive_message(QueueUrl=queue, MaxNumberOfMessages=10,
                                           WaitTimeSeconds=5, VisibilityTimeout=10).get('Messages', []):
            body = json.loads(message['Body'])
            if body.get('execution_id') in expected:
                found[body['execution_id']] = body
        return found if found.keys() == expected else None
    return poll(check, seconds=100, interval=1)


def main():
    if not __debug__:
        raise SystemExit('Run with normal Python assertion checking enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    add_target(parser)
    parser.add_argument('--run-live', action='store_true', required=True)
    args = parser.parse_args()
    session, cf = target(args)
    _, outputs = stack_info(cf, args.stack)
    if outputs.get('DemoFailuresEnabled') != 'true':
        raise SystemExit('Deploy with EnableDemoFailures=true before running the suite')
    s3, sfn, logs, sqs = (session.client(service) for service in ('s3', 'stepfunctions', 'logs', 'sqs'))
    table = session.resource('dynamodb').Table(outputs['DocumentsTable'])
    fixture = (EXAMPLES / CASES['valid'][0]).read_bytes()
    existing = table.get_item(Key={'document_id': hashlib.sha256(fixture).hexdigest()}, ConsistentRead=True)
    if 'Item' in existing:
        raise SystemExit('The valid fixture already has a claim. Use a fresh acceptance stack.')
    started = datetime.now(timezone.utc)
    run_id = uuid4().hex[:12]
    evidence = {'status': 'incomplete', 'started_at': started.isoformat(), 'region': args.region,
                'stack': args.stack, 'model_id': outputs['ModelIdUsed'], 'run_id': run_id,
                'results': {}}
    path = ROOT / 'artifacts' / f'v02-live-{run_id}.json'
    path.parent.mkdir(exist_ok=True)
    uploads = {}
    review = set()

    def upload(case):
        file, mime, _, _ = CASES[case]
        data = (EXAMPLES / file).read_bytes()
        key = f'incoming/{run_id}/{case}/{Path(file).name}'
        put = s3.put_object(Bucket=outputs['InputBucketName'], Key=key, Body=data, ContentType=mime)
        uploads[key] = {'case': case, 'version': put['VersionId'], 'sha256': hashlib.sha256(data).hexdigest()}
        evidence['results'][case] = {'key': key, **uploads[key]}
        return key

    try:
        first = upload('valid')
        first_runs = poll(lambda: find_executions(sfn, outputs, {first: uploads[first]}, started))[first]
        assert any(json.loads(item.get('output') or '{}').get('outcome') == 'ACCEPTED'
                   for item in first_runs), first_runs[0]['executionArn']
        for case in list(CASES)[1:]:
            upload(case)
        executions = poll(lambda: find_executions(sfn, outputs, uploads, started))
        for key, upload_info in uploads.items():
            case, version, digest = (upload_info[name] for name in ('case', 'version', 'sha256'))
            _, _, outcome, number = CASES[case]
            candidates = executions[key]
            if outcome == 'ACCEPTED':
                run = next((item for item in candidates
                            if json.loads(item.get('output') or '{}').get('outcome') == 'ACCEPTED'), candidates[0])
            elif outcome == 'ReviewRequired':
                run = next((item for item in candidates if item.get('error') == outcome), candidates[0])
            else:
                run = candidates[0]
            arn = run['executionArn']
            record = evidence['results'][case]
            record.update(execution_id=arn, aws_status=run['status'])
            history = list(pages(sfn, 'get_execution_history', 'events', executionArn=arn,
                                 includeExecutionData=False))
            record['history_event_types'] = [item['type'] for item in history]
            records = poll(lambda: traces(logs, outputs['ProcessorLogGroupName'], started, arn, LOG_EVENTS[case]), 120)
            record['logs'] = records
            if outcome == 'ReviewRequired':
                assert run['status'] == 'FAILED' and run.get('error') == outcome, arn
                review.add(arn)
                review_record = next(line for line in records if line['event'] == 'review_required')
                row = table.get_item(Key={'document_id': review_record['review_id']}, ConsistentRead=True)['Item']
                assert row['status'] == 'REVIEW_REQUIRED' and row['source']['version_id'] == version, arn
                expected_code = {'unsupported': 'UNSUPPORTED_FORMAT', 'invalid': 'INVALID_EXTRACTION',
                                 'totals': 'INVALID_EXTRACTION', 'exhausted': 'INJECTED_TRANSIENT'}[case]
                assert any(line.get('code') == expected_code for line in records), arn
                if case == 'exhausted':
                    assert len([line for line in records if line['event'] == 'injected_transient']) == 3, arn
                continue
            assert run['status'] == 'SUCCEEDED' and json.loads(run['output'])['outcome'] == outcome, arn
            row = table.get_item(Key={'document_id': digest}, ConsistentRead=True)['Item']
            expected_version = uploads[first]['version'] if case == 'duplicate' else version
            assert row['status'] == 'ACCEPTED' and row['source']['version_id'] == expected_version, arn
            if case == 'duplicate':
                assert not any(line['event'] == 'bedrock_completed' for line in records), arn
            else:
                body = s3.get_object(Bucket=outputs['OutputBucketName'], Key=row['output_key'])['Body']
                try:
                    payload = json.load(body)
                finally:
                    body.close()
                assert (payload['document_id'], payload['source']['version_id'], payload['model_id']) == (
                    digest, version, outputs['ModelIdUsed']), arn
                match_invoice(payload['invoice'], number)
                record['validated_json'] = payload
                api_events = {'bedrock_completed'} | ({'textract_completed'} if case == 'scan' else set())
                assert all(any(line['event'] == event and line.get('request_id') for line in records)
                           for event in api_events), arn
            versions = list(pages(s3, 'list_object_versions', 'Versions',
                                  Bucket=outputs['OutputBucketName'], Prefix=row['output_key']))
            assert len(versions) == 1, arn
        evidence['review_messages'] = messages(sqs, outputs['ReviewQueueUrl'], review)
        assert all(body.get('source', {}).get('key') in uploads for body in evidence['review_messages'].values())
        dlq = sqs.get_queue_attributes(QueueUrl=outputs['DeliveryDeadLetterQueueUrl'],
                                       AttributeNames=['ApproximateNumberOfMessages'])
        assert dlq['Attributes']['ApproximateNumberOfMessages'] == '0', 'Unexpected delivery DLQ messages'
        evidence['status'] = 'passed'
    finally:
        path.write_text(json.dumps(evidence, indent=2) + '\n')
        print(f'Acceptance status: {evidence["status"]}. Evidence: {path}')


if __name__ == '__main__':
    main()
