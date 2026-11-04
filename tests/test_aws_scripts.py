"""Offline safety checks for opt-in live scripts. No AWS requests are sent."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', ['verify_aws', 'cleanup_aws'])
def test_account_guard_prevents_mutations(monkeypatch, name):
    module = load(name)
    session = Mock()
    sts = Mock()
    sts.get_caller_identity.return_value = {'Account': '111111111111'}
    session.client.return_value = sts
    monkeypatch.setattr(module.boto3, 'Session', Mock(return_value=session))
    args = [name, '--stack', 'invoice-v01', '--region', 'us-east-1', '--confirm-account', '222222222222']
    if name == 'cleanup_aws': args.append('--delete-all-project-data')
    monkeypatch.setattr(sys, 'argv', args)
    with pytest.raises(SystemExit, match='Account mismatch'):
        module.main()
    assert session.client.call_args_list[0].args == ('sts',)
    assert session.client.call_count == 1


@pytest.mark.parametrize('name', ['verify_aws', 'cleanup_aws'])
def test_wrong_stack_rejected(monkeypatch, name):
    module = load(name)
    session, sts, cf = Mock(), Mock(), Mock()
    sts.get_caller_identity.return_value = {'Account': '111111111111'}
    cf.describe_stacks.return_value = {'Stacks': [{'Description': 'unrelated project'}]}
    session.client.side_effect = lambda service: {'sts': sts, 'cloudformation': cf}[service]
    monkeypatch.setattr(module.boto3, 'Session', Mock(return_value=session))
    args = [name, '--stack', 'other', '--region', 'us-east-1', '--confirm-account', '111111111111']
    if name == 'cleanup_aws': args.append('--delete-all-project-data')
    monkeypatch.setattr(sys, 'argv', args)
    with pytest.raises(SystemExit, match='Unexpected stack'):
        module.main()
    assert session.client.call_count == 2


def test_delete_every_version_and_marker():
    module = load('cleanup_aws')
    s3 = Mock()
    s3.list_object_versions.side_effect = [
        {'Versions': [{'Key': 'a', 'VersionId': 'v1'}], 'DeleteMarkers': [{'Key': 'a', 'VersionId': 'm1'}]},
        {'Versions': [{'Key': 'a', 'VersionId': 'v2'}]}, {},
    ]
    s3.list_objects_v2.side_effect = [{'Contents': [{'Key': 'unversioned'}]}, {}]
    s3.delete_objects.return_value = {}
    module.empty_bucket(s3, 'project')
    deleted = [obj for call in s3.delete_objects.call_args_list for obj in call.kwargs['Delete']['Objects']]
    assert deleted == [{'Key': 'a', 'VersionId': 'v1'}, {'Key': 'a', 'VersionId': 'm1'},
                       {'Key': 'a', 'VersionId': 'v2'}, {'Key': 'unversioned'}]


def test_delete_errors_stop_cleanup():
    module = load('cleanup_aws')
    s3 = Mock()
    s3.list_object_versions.return_value = {'Versions': [{'Key': 'a', 'VersionId': 'v1'}]}
    s3.delete_objects.return_value = {'Errors': [{'Code': 'AccessDenied'}]}
    with pytest.raises(RuntimeError, match='could not be deleted'):
        module.empty_bucket(s3, 'project')
    s3.delete_bucket.assert_not_called()


def test_bucket_ownership_guard(monkeypatch):
    module = load('cleanup_aws')
    session, sts, cf = Mock(), Mock(), Mock()
    sts.get_caller_identity.return_value = {'Account': '111111111111'}
    cf.describe_stacks.return_value = {'Stacks': [{
        'Description': 'Synthetic text invoice pipeline v0.1',
        'Outputs': [{'OutputKey': 'InputBucketName', 'OutputValue': 'input'},
                    {'OutputKey': 'OutputBucketName', 'OutputValue': 'unowned'}]}]}
    cf.get_paginator.return_value.paginate.return_value = [{'StackResourceSummaries': [
        {'ResourceType': 'AWS::S3::Bucket', 'PhysicalResourceId': 'input'}]}]
    session.client.side_effect = lambda service: {'sts': sts, 'cloudformation': cf}[service]
    monkeypatch.setattr(module.boto3, 'Session', Mock(return_value=session))
    monkeypatch.setattr(sys, 'argv', ['cleanup', '--stack', 'invoice-v01', '--region', 'us-east-1',
                                    '--confirm-account', '111111111111', '--delete-all-project-data'])
    with pytest.raises(SystemExit, match='ownership check failed'):
        module.main()
    cf.delete_stack.assert_not_called()


def test_cleanup_pauses_then_deletes_owned_resources(monkeypatch):
    import time
    module = load('cleanup_aws')
    session, sts, cf, s3, function, waiter = [Mock() for _ in range(6)]
    sts.get_caller_identity.return_value = {'Account': '111111111111'}
    cf.describe_stacks.return_value = {'Stacks': [{
        'Description': 'Synthetic text invoice pipeline v0.1', 'StackId': 'stack-id',
        'Outputs': [{'OutputKey': key, 'OutputValue': value} for key, value in
                    [('InputBucketName', 'input'), ('OutputBucketName', 'output'), ('FunctionName', 'processor')]]}]}
    cf.get_paginator.return_value.paginate.return_value = [{'StackResourceSummaries': [
        {'ResourceType': 'AWS::S3::Bucket', 'PhysicalResourceId': name} for name in ('input', 'output')]}]
    cf.get_waiter.return_value = waiter
    s3.list_object_versions.return_value = {}
    s3.list_objects_v2.return_value = {}
    session.client.side_effect = lambda service: {'sts': sts, 'cloudformation': cf, 's3': s3, 'lambda': function}[service]
    monkeypatch.setattr(module.boto3, 'Session', Mock(return_value=session))
    monkeypatch.setattr(time, 'sleep', Mock())
    monkeypatch.setattr(sys, 'argv', ['cleanup', '--stack', 'invoice-v01', '--region', 'us-east-1',
                                    '--confirm-account', '111111111111', '--delete-all-project-data'])
    ordering = Mock()
    ordering.attach_mock(function.put_function_concurrency, 'pause')
    ordering.attach_mock(cf.delete_stack, 'delete_stack')
    ordering.attach_mock(waiter.wait, 'wait_for_delete')
    ordering.attach_mock(s3.delete_bucket, 'delete_bucket')
    module.main()
    assert [call[0] for call in ordering.mock_calls] == [
        'pause', 'delete_stack', 'wait_for_delete', 'delete_bucket', 'delete_bucket']
    s3.put_bucket_notification_configuration.assert_called_once_with(
        Bucket='input', NotificationConfiguration={})


def test_live_verifier_checks_outputs_and_logs_offline(monkeypatch, tmp_path):
    import io
    import json
    from datetime import datetime, timezone
    module = load('verify_aws')
    session, sts, cf, s3, logs = [Mock() for _ in range(5)]
    sts.get_caller_identity.return_value = {'Account': '111111111111'}
    cf.describe_stacks.return_value = {'Stacks': [{
        'Description': 'Synthetic text invoice pipeline v0.1',
        'Outputs': [{'OutputKey': key, 'OutputValue': value} for key, value in
                    [('InputBucketName', 'input'), ('OutputBucketName', 'output'),
                     ('FunctionName', 'processor'), ('ModelIdUsed', 'model')]]}]}
    (tmp_path / 'examples').mkdir()
    for name in ('invoice.txt', 'expected.json'):
        (tmp_path / 'examples' / name).write_bytes((ROOT / 'examples' / name).read_bytes())
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    records = {}
    def list_pages(**kwargs):
        kind = 'valid' if kwargs['Prefix'] == 'validated/' else 'invalid'
        upload = s3.put_object.call_args_list[0 if kind == 'valid' else 1]
        data = {'source': {'key': upload.kwargs['Key']}, 'trace_id': kind, 'request_id': kind}
        if kind == 'valid':
            data['invoice'] = module.validate(json.loads((ROOT / 'examples/expected.json').read_text()))
        else:
            data.update(stage='document', error_type='UnicodeDecodeError')
        key = kwargs['Prefix'] + kind + '.json'
        records[key] = data
        return [{'Contents': [{'Key': key, 'LastModified': datetime.now(timezone.utc)}]}]
    s3.get_paginator.return_value.paginate.side_effect = list_pages
    s3.get_object.side_effect = lambda **kw: {'Body': io.BytesIO(json.dumps(records[kw['Key']]).encode())}
    logs.get_paginator.return_value.paginate.return_value = [{'events': [{'message': 'valid invalid'}]}]
    session.client.side_effect = lambda service: {'sts': sts, 'cloudformation': cf, 's3': s3, 'logs': logs}[service]
    monkeypatch.setattr(module.boto3, 'Session', Mock(return_value=session))
    monkeypatch.setattr(sys, 'argv', ['verify', '--stack', 'invoice-v01', '--region', 'us-east-1',
                                    '--confirm-account', '111111111111'])
    module.main()
    evidence = json.loads(next((tmp_path / 'artifacts').glob('*.json')).read_text())
    assert evidence['status'] == 'passed'
    assert len(evidence['results']) == 2
    assert s3.put_object.call_count == 2
