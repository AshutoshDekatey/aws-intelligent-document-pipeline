"""Shared account and stack guards for the operator-run scripts."""
import boto3

DESCRIPTION = 'Synthetic financial document pipeline v0.2'


def add_target(parser):
    parser.add_argument('--stack', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--confirm-account', required=True)


def target(args):
    session = boto3.Session(region_name=args.region)
    account = session.client('sts').get_caller_identity()['Account']
    if account != args.confirm_account:
        raise SystemExit('Account mismatch')
    return session, session.client('cloudformation')


def stack_info(cf, stack):
    info = cf.describe_stacks(StackName=stack)['Stacks'][0]
    if info.get('Description') != DESCRIPTION:
        raise SystemExit('Unexpected stack description')
    outputs = {item['OutputKey']: item['OutputValue'] for item in info.get('Outputs', [])}
    return info, outputs
