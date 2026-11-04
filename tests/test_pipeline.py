import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from app import process, extract, MAX_BYTES
from validation import validate, InvalidInvoice

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def invoice():
    return json.loads((ROOT / 'examples/expected.json').read_text())

@pytest.fixture
def aws(invoice):
    s3, model = Mock(), Mock()
    s3.get_object.side_effect = lambda **kw: {'Body': io.BytesIO((ROOT / 'examples/invoice.txt').read_bytes())}
    model.converse.return_value = {'stopReason': 'end_turn', 'output': {'message': {'content': [{'text': json.dumps(invoice)}]}}}
    return s3, model


def event(key='incoming/test+invoice.txt'):
    return {'Records': [{'s3': {'bucket': {'name': 'input'}, 'object': {'key': key, 'versionId': 'v1', 'sequencer': '001'}}}]}


def run(aws, ev=None):
    return process(ev or event(), SimpleNamespace(aws_request_id='request-1'), *aws, 'output', 'model')


def test_success(aws):
    result = run(aws)
    s3, model = aws
    s3.get_object.assert_called_once_with(Bucket='input', Key='incoming/test invoice.txt', VersionId='v1')
    saved = json.loads(s3.put_object.call_args.kwargs['Body'])
    assert saved['invoice']['total'] == '34.10'
    assert saved['source']['version_id'] == 'v1'
    assert saved['trace_id'] == result['results'][0]['trace_id']
    assert s3.put_object.call_args.kwargs['Key'].startswith('validated/')
    assert model.converse.call_args.kwargs['modelId'] == 'model'


@pytest.mark.parametrize('field,value', [('invoice_date', '2026-02-30'), ('invoice_date', '20261101'), ('currency', 'XYZ'), ('vendor', ''), ('invoice_number', None), ('total', '35.00'), ('subtotal', '30.00'), ('tax', '-1'), ('total', 'NaN'), ('total', True), ('tax', '3.101'), ('line_items', [])])
def test_reject_fields(invoice, field, value):
    invoice[field] = value
    with pytest.raises(InvalidInvoice):
        validate(invoice)


@pytest.mark.parametrize('field,value', [('quantity', '0'), ('quantity', '-1'), ('amount', '24'), ('unit_price', 'Infinity'), ('description', '')])
def test_reject_line(invoice, field, value):
    invoice['line_items'][0][field] = value
    with pytest.raises(InvalidInvoice):
        validate(invoice)


def test_schema_and_rounding(invoice):
    assert validate(invoice)['total'] == '34.10'
    invoice['extra'] = 1
    with pytest.raises(InvalidInvoice): validate(invoice)
    del invoice['extra']
    invoice['line_items'] = [dict(description='fraction', quantity='0.5', unit_price='0.01', amount='0.01')]
    invoice.update(subtotal='0.01', tax='0.00', total='0.01')
    assert validate(invoice)['total'] == '0.01'


@pytest.mark.parametrize('raw', [b'', b'\xff', b'\x00bad', b' ' * 20, b'a' * (MAX_BYTES + 1)])
def test_malformed_document(aws, raw):
    aws[0].get_object.side_effect = lambda **kw: {'Body': io.BytesIO(raw)}
    assert run(aws)['results'][0]['stage'] == 'document'
    aws[1].converse.assert_not_called()
    assert aws[0].put_object.call_args.kwargs['Key'].startswith('errors/')


@pytest.mark.parametrize('raw', ['not JSON', '{"vendor":1,"vendor":2}'])
def test_bad_model_json_retries(aws, raw):
    aws[1].converse.return_value['output']['message']['content'][0]['text'] = raw
    with pytest.raises(RuntimeError): run(aws)
    assert json.loads(aws[0].put_object.call_args.kwargs['Body'])['stage'] == 'model'


def test_model_failure_no_sensitive_logs(aws, caplog):
    aws[1].converse.side_effect = ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'SENSITIVE'}}, 'Converse')
    with pytest.raises(RuntimeError): run(aws)
    assert 'SENSITIVE' not in caplog.text
    assert 'request-1' in caplog.text


def test_validation_terminal(aws):
    aws[1].converse.return_value['output']['message']['content'][0]['text'] = '{}'
    assert run(aws)['results'][0]['stage'] == 'validation'


def test_truncated_response(aws):
    aws[1].converse.return_value['stopReason'] = 'max_tokens'
    with pytest.raises(RuntimeError): run(aws)


def test_output_failure_retries(aws):
    aws[0].put_object.side_effect = [OSError('failure'), None]
    with pytest.raises(RuntimeError): run(aws)
    assert aws[0].put_object.call_count == 2


def test_error_write_failure_propagates(aws):
    aws[0].get_object.side_effect = OSError('failure')
    aws[0].put_object.side_effect = OSError('failure')
    with pytest.raises(OSError): run(aws)


def test_duplicate_and_versions(aws):
    run(aws); first = aws[0].put_object.call_args.kwargs['Key']
    run(aws); assert aws[0].put_object.call_args.kwargs['Key'] == first
    ev = event(); ev['Records'][0]['s3']['object']['versionId'] = 'v2'
    run(aws, ev); assert aws[0].put_object.call_args.kwargs['Key'] != first


def test_multiple_records_continue_after_failure(aws):
    ev = event('incoming/bad.pdf'); ev['Records'] += event()['Records']
    assert [r['status'] for r in run(aws, ev)['results']] == ['failed', 'validated']


def test_model_decimal_precision(aws):
    aws[1].converse.return_value['output']['message']['content'][0]['text'] = '{"value": 1.0000000000000001}'
    assert extract(aws[1], 'model', 'synthetic')['value'] == '1.0000000000000001'


def test_real_sdk_converse_contract(invoice, monkeypatch):
    import boto3
    from botocore.stub import Stubber
    from app import PROMPT
    # Explicit dummy credentials prevent any credential discovery/network calls.
    import botocore.session
    # Isolate SDK configuration as well as service calls; preserve process guards.
    monkeypatch.setattr(botocore.session.Session, 'get_scoped_config', lambda self: {})
    offline = botocore.session.Session()
    session = boto3.Session(botocore_session=offline)
    client = session.client('bedrock-runtime', region_name='us-east-1',
                          aws_access_key_id='synthetic', aws_secret_access_key='synthetic')
    with Stubber(client) as stub:
        stub.add_response('converse', {
            'stopReason': 'end_turn',
            'output': {'message': {'role': 'assistant', 'content': [{'text': json.dumps(invoice)}]}},
            'usage': {'inputTokens': 1, 'outputTokens': 1, 'totalTokens': 2},
            'metrics': {'latencyMs': 1},
        }, {
            'modelId': 'model', 'system': [{'text': PROMPT}],
            'messages': [{'role': 'user', 'content': [{'text': 'Invoice document:\nsynthetic'}]}],
            'inferenceConfig': {'maxTokens': 4096, 'temperature': 0},
        })
        assert validate(extract(client, 'model', 'synthetic'))['total'] == '34.10'
        stub.assert_no_pending_responses()
