# Verification evidence

Executed in Codex Cloud on 2026-11-04 using Python 3.12.14:

- `pytest -q`: 35 passed. Mocked S3/Bedrock pipeline tests cover valid output,
  source versions and key decoding, malformed/oversized/binary input, field and
  arithmetic validation, duplicate events, multiple records, model errors,
  invalid JSON, truncation, failed writes, sensitive-log exclusion and decimal
  precision. A botocore Stubber test checks the actual Converse API contract.
  SDK configuration is isolated in that test; no service requests are sent.
- `pip check`: no broken requirements.
- Initial `sam validate --lint`: valid SAM template. It also emitted warnings
  because the home-directory metadata location is read-only.
- Subsequent SAM validation/build attempts: blocked by the environment's missing
  guard profile `__oai_no_aws_identity__`. The initial build also failed package
  resolution in the networking sandbox. SAM build is **not verified**.
- Local Lambda dependency packaging with `pip install --target` succeeded;
  imports of the packaged handler and boto3 passed in isolated Python. This
  checks local packaging, not the SAM transform/build or a Lambda invocation.
- No AWS account API, deployment, resource creation or live model invocation.
- GitHub Actions configuration is supplied; its remote execution is unverified.

SAM supports `__SAM_CLI_APP_DIR=/tmp/invoice-sam-config` for local metadata when
home is read-only, and `SAM_CLI_TELEMETRY=0` disables telemetry. These settings do
not resolve the intentionally unavailable AWS guard profile; preserve that guard.
A fresh approved deployment environment must run README's SAM checks before
reviewing and applying a changeset.
