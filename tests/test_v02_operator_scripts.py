import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def load(script, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(script, SCRIPTS / f'{script}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('script,flag', [('accept_v02', '--run-live'), ('destroy_v02', '--delete-all-project-data')])
def test_account_mismatch_stops_before_looking_up_stack(monkeypatch, script, flag):
    module = load(script, monkeypatch)
    target_module = sys.modules['aws_v02']
    session = Mock()
    session.client.return_value.get_caller_identity.return_value = {'Account': '111111111111'}
    monkeypatch.setattr(target_module.boto3, 'Session', Mock(return_value=session))
    monkeypatch.setattr(sys, 'argv', [script, '--stack', 'finance-v02', '--region', 'us-east-1',
                                    '--confirm-account', '999999999999', flag])
    with pytest.raises(SystemExit, match='Account mismatch'):
        module.main()
    session.client.assert_called_once_with('sts')


def test_access_denied_is_not_a_successful_cleanup_check(monkeypatch):
    cleanup = load('destroy_v02', monkeypatch)
    session = Mock()
    head = session.client.return_value.head_bucket
    head.side_effect = ClientError({'Error': {'Code': 'AccessDenied'}}, 'HeadBucket')
    with pytest.raises(ClientError, match='AccessDenied'):
        cleanup.remaining(session, [('AWS::S3::Bucket', 'owned')])
    head.side_effect = ClientError({'Error': {'Code': '404'}}, 'HeadBucket')
    assert cleanup.remaining(session, [('AWS::S3::Bucket', 'owned')]) == []
