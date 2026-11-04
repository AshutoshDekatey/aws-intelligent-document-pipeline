"""DESTRUCTIVE opt-in cleanup of this project's stack and retained invoice buckets."""
import argparse

import boto3


def empty_bucket(s3, bucket):
    # Re-list after every delete batch so changing pagination cannot skip versions.
    while True:
        page = s3.list_object_versions(Bucket=bucket, MaxKeys=1000)
        objects = [{'Key': obj['Key'], 'VersionId': obj['VersionId']}
                   for group in ('Versions', 'DeleteMarkers') for obj in page.get(group, [])]
        if not objects:
            break
        for offset in range(0, len(objects), 1000):
            response = s3.delete_objects(Bucket=bucket, Delete={'Objects': objects[offset:offset + 1000]})
            if response.get('Errors'):
                raise RuntimeError('Some versions could not be deleted; inspect S3 permissions/retention')
    # Also handles never-versioned output objects.
    while True:
        page = s3.list_objects_v2(Bucket=bucket, MaxKeys=1000)
        objects = [{'Key': obj['Key']} for obj in page.get('Contents', [])]
        if not objects:
            break
        response = s3.delete_objects(Bucket=bucket, Delete={'Objects': objects})
        if response.get('Errors'):
            raise RuntimeError('Some objects could not be deleted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--confirm-account', required=True)
    parser.add_argument('--delete-all-project-data', action='store_true', required=True)
    args = parser.parse_args()
    session = boto3.Session(region_name=args.region)
    if session.client('sts').get_caller_identity()['Account'] != args.confirm_account:
        raise SystemExit('Account mismatch; nothing deleted')
    cf = session.client('cloudformation')
    stack = cf.describe_stacks(StackName=args.stack)['Stacks'][0]
    if stack.get('Description') != 'Synthetic text invoice pipeline v0.1':
        raise SystemExit('Unexpected stack; nothing deleted')
    outputs = {item['OutputKey']: item['OutputValue'] for item in stack['Outputs']}
    buckets = [outputs['InputBucketName'], outputs['OutputBucketName']]
    resources = []
    for page in cf.get_paginator('list_stack_resources').paginate(StackName=args.stack):
        resources.extend(page['StackResourceSummaries'])
    owned = {r['PhysicalResourceId'] for r in resources if r['ResourceType'] == 'AWS::S3::Bucket'}
    if set(buckets) != owned:
        raise SystemExit('Bucket ownership check failed; nothing deleted')
    function = session.client('lambda')
    # Stop processing before deleting data. Stop all external uploads first.
    function.put_function_concurrency(FunctionName=outputs['FunctionName'], ReservedConcurrentExecutions=0)
    s3 = session.client('s3')
    s3.put_bucket_notification_configuration(Bucket=buckets[0], NotificationConfiguration={})
    # Wait until any already-running invocation can no longer write outputs.
    import time
    print('Processing paused. Waiting 130 seconds for in-flight Lambda invocations to finish.')
    time.sleep(130)
    cf.delete_stack(StackName=stack['StackId'])
    cf.get_waiter('stack_delete_complete').wait(StackName=stack['StackId'])
    for bucket in buckets:
        empty_bucket(s3, bucket)
        s3.delete_bucket(Bucket=bucket)
        print(f'Deleted project bucket: {bucket}')
    print('Stack and invoice buckets deleted. Separately inspect SAM deployment artifacts,')
    print('shared SAM managed resources, CloudShell files, budgets and delayed billing data.')


if __name__ == '__main__':
    main()
