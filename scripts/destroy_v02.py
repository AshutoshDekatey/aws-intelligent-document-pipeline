"""Delete an identified v0.2 stack and verify service-level removal."""
import argparse
import json
import time
from pathlib import Path

from botocore.exceptions import ClientError

from aws_v02 import add_target, stack_info, target
from cleanup_aws import empty_bucket

PROBES = {
    'AWS::S3::Bucket': ('s3', 'head_bucket', 'Bucket', {'404', 'NoSuchBucket', 'NotFound'}),
    'AWS::Lambda::Function': ('lambda', 'get_function', 'FunctionName', {'ResourceNotFoundException'}),
    'AWS::StepFunctions::StateMachine': ('stepfunctions', 'describe_state_machine', 'stateMachineArn',
                                         {'StateMachineDoesNotExist'}),
    'AWS::DynamoDB::Table': ('dynamodb', 'describe_table', 'TableName', {'ResourceNotFoundException'}),
    'AWS::SQS::Queue': ('sqs', 'get_queue_attributes', 'QueueUrl',
                        {'AWS.SimpleQueueService.NonExistentQueue', 'QueueDoesNotExist'}),
    'AWS::Events::Rule': ('events', 'describe_rule', 'Name', {'ResourceNotFoundException'}),
    'AWS::IAM::Role': ('iam', 'get_role', 'RoleName', {'NoSuchEntity'}),
}


def resources(cf, stack_id):
    for page in cf.get_paginator('list_stack_resources').paginate(StackName=stack_id):
        yield from page['StackResourceSummaries']


def remaining(session, inventory):
    live = []
    for kind, name in inventory:
        if kind in PROBES:
            service, op, parameter, absent = PROBES[kind]
            try:
                getattr(session.client(service), op)(**{parameter: name})
            except ClientError as exc:
                if exc.response['Error']['Code'] in absent:
                    continue
                raise
        elif kind == 'AWS::Logs::LogGroup':
            groups = session.client('logs').get_paginator('describe_log_groups').paginate(logGroupNamePrefix=name)
            if not any(g['logGroupName'] == name for page in groups for g in page.get('logGroups', [])):
                continue
        elif kind == 'AWS::CloudWatch::Alarm':
            alarms = session.client('cloudwatch').describe_alarms(AlarmNames=[name])
            if not alarms['MetricAlarms']:
                continue
        else:
            continue
        live.append((kind, name))
    return live


def drain(events, sfn, rule, machine):
    events.disable_rule(Name=rule)
    # An in-flight delivery can retry for 300 seconds. Keep the rule disabled while draining.
    time.sleep(310)
    deadline = time.monotonic() + 460
    while sfn.list_executions(stateMachineArn=machine, statusFilter='RUNNING', maxResults=1)['executions']:
        if time.monotonic() >= deadline:
            raise TimeoutError('Active executions remain. Inspect Step Functions before deleting buckets.')
        time.sleep(10)
    time.sleep(10)


def verify(session, inventory):
    for _ in range(12):
        live = remaining(session, inventory)
        if not live:
            print('Service-level cleanup verified for inventoried resources.')
            return
        time.sleep(10)
    raise SystemExit(f'Resources still visible: {live}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_target(parser)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--delete-all-project-data', action='store_true')
    mode.add_argument('--verify-only', action='store_true')
    parser.add_argument('--manifest', type=Path, default=Path('artifacts/v02-cleanup.json'))
    args = parser.parse_args()
    session, cf = target(args)
    expected = {'account': args.confirm_account, 'region': args.region, 'stack': args.stack}
    if args.verify_only:
        manifest = json.loads(args.manifest.read_text())
        if any(manifest.get(k) != v for k, v in expected.items()):
            raise SystemExit('Manifest does not match account, region and stack')
        cf.get_waiter('stack_delete_complete').wait(StackName=manifest['stack_id'],
                                                   WaiterConfig={'Delay': 10, 'MaxAttempts': 60})
        verify(session, manifest['resources'])
        return
    stack, outputs = stack_info(cf, args.stack)
    required = {'InputBucketName', 'OutputBucketName', 'UploadRuleName', 'StateMachineArn'}
    if not required <= outputs.keys():
        raise SystemExit('Stack outputs unavailable. Use the partial-deployment cleanup steps in the guide.')
    inventory = [(item['ResourceType'], item['PhysicalResourceId'])
                 for item in resources(cf, stack['StackId'])
                 if 'PhysicalResourceId' in item and item['ResourceStatus'] != 'DELETE_COMPLETE']
    buckets = [outputs['InputBucketName'], outputs['OutputBucketName']]
    if any(('AWS::S3::Bucket', bucket) not in inventory for bucket in buckets):
        raise SystemExit('Bucket ownership check failed')
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({**expected, 'stack_id': stack['StackId'], 'resources': inventory}, indent=2))
    drain(session.client('events'), session.client('stepfunctions'), outputs['UploadRuleName'], outputs['StateMachineArn'])
    s3 = session.client('s3')
    for bucket in buckets:
        empty_bucket(s3, bucket)
    cf.delete_stack(StackName=stack['StackId'])
    cf.get_waiter('stack_delete_complete').wait(StackName=stack['StackId'],
                                               WaiterConfig={'Delay': 10, 'MaxAttempts': 60})
    verify(session, inventory)
    print('Clean up the separate packaging bucket or this experiment’s SAM artifact prefix using the guide.')


if __name__ == '__main__':
    main()
