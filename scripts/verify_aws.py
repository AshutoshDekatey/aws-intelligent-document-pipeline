"""Opt-in LIVE AWS test. Uploads two synthetic objects and incurs AWS charges."""
import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from validation import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--confirm-account', required=True, help='Expected 12-digit AWS account ID')
    args = parser.parse_args()
    session = boto3.Session(region_name=args.region)
    account = session.client('sts').get_caller_identity()['Account']
    if account != args.confirm_account:
        raise SystemExit('Account mismatch; no uploads performed')
    stack = session.client('cloudformation').describe_stacks(StackName=args.stack)['Stacks'][0]
    if stack.get('Description') != 'Synthetic text invoice pipeline v0.1':
        raise SystemExit('Unexpected stack description; no uploads performed')
    outputs = {item['OutputKey']: item['OutputValue'] for item in stack['Outputs']}
    s3 = session.client('s3')
    logs = session.client('logs')
    run_id = str(uuid.uuid4())
    keys = {'valid': f'incoming/live-{run_id}.txt', 'invalid': f'incoming/invalid-{run_id}.txt'}
    started = int(time.time() * 1000)
    # Invalid UTF-8 deterministically tests rejection before model invocation.
    s3.put_object(Bucket=outputs['InputBucketName'], Key=keys['valid'],
                  Body=(ROOT / 'examples/invoice.txt').read_bytes(), ContentType='text/plain')
    s3.put_object(Bucket=outputs['InputBucketName'], Key=keys['invalid'],
                  Body=b'\xff\x00synthetic malformed input', ContentType='text/plain')
    found = {}
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline and len(found) < 2:
        for prefix in ('validated/', 'errors/'):
            for page in s3.get_paginator('list_objects_v2').paginate(Bucket=outputs['OutputBucketName'], Prefix=prefix):
                for obj in page.get('Contents', []):
                    if obj['LastModified'].timestamp() * 1000 < started - 1000:
                        continue
                    response = s3.get_object(Bucket=outputs['OutputBucketName'], Key=obj['Key'])
                    try:
                        data = json.loads(response['Body'].read())
                    finally:
                        response['Body'].close()
                    for kind, key in keys.items():
                        if data.get('source', {}).get('key') == key:
                            found[kind] = {'object_key': obj['Key'], 'record': data}
        if 'valid' in found and 'invoice' not in found['valid']['record']:
            raise RuntimeError('Valid fixture failed; inspect correlated errors and CloudWatch')
        if len(found) < 2:
            time.sleep(5)
    if len(found) != 2:
        raise TimeoutError('Expected both outputs within 300s; inspect S3 notifications and Lambda logs')
    expected = validate(json.loads((ROOT / 'examples/expected.json').read_text()))
    if found['valid']['record'].get('invoice') != expected:
        raise AssertionError('Extracted fields differ from synthetic fixture; inspect JSON manually')
    invalid = found['invalid']['record']
    if invalid.get('stage') != 'document' or invalid.get('error_type') != 'UnicodeDecodeError':
        raise AssertionError('Malformed fixture did not produce the expected document error')
    # Allow CloudWatch delivery to catch up and verify the same trace IDs there.
    trace_ids = {value['record']['trace_id'] for value in found.values()}
    seen = set()
    log_deadline = time.monotonic() + 120
    while time.monotonic() < log_deadline and seen != trace_ids:
        for page in logs.get_paginator('filter_log_events').paginate(
                logGroupName=f"/aws/lambda/{outputs['FunctionName']}", startTime=started):
            for event in page.get('events', []):
                seen.update(trace for trace in trace_ids if trace in event['message'])
        if seen != trace_ids:
            time.sleep(5)
    if seen != trace_ids:
        raise AssertionError('Outputs found but matching CloudWatch traces not observed')
    evidence = dict(verified_at=datetime.now(timezone.utc).isoformat(), account=account,
                    region=args.region, stack=args.stack, model=outputs.get('ModelIdUsed'),
                    run_id=run_id, status='passed',
                    results={kind: {'object_key': value['object_key'],
                                    'trace_id': value['record']['trace_id'],
                                    'request_id': value['record']['request_id']}
                             for kind, value in found.items()})
    target = ROOT / 'artifacts' / f'aws-verification-{run_id}.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2) + '\n')
    print(f'LIVE AWS checks passed. Evidence: {target}')
    print('Resources remain deployed. Follow docs/cleanup.md to stop and remove them.')


if __name__ == '__main__':
    main()
