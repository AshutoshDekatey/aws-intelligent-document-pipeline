# Verify the real AWS pipeline

Requires successful [deployment](deployment.md), its tools, and the same shell
variables. These steps incur real S3/Lambda/Bedrock/log charges. The script uses
your AWS identity and never substitutes mocked AWS clients.

## Automated live smoke test

From the repository root in CloudShell/the configured workstation:

```bash
source /tmp/invoice-tools/bin/activate
python scripts/verify_aws.py --stack "$STACK" --region "$AWS_REGION" \
  --confirm-account "$EXPECTED_ACCOUNT"
```

The script checks account ID and project stack description before uploading.
It uploads the synthetic valid invoice and a deliberately malformed UTF-8 text
object under unique `incoming/*.txt` keys. The actual S3 notifications must invoke
Lambda. It polls S3 for up to five minutes, compares every validated field with
examples/expected.json, checks a document-stage error for the malformed input,
and waits up to two more minutes for both trace IDs in CloudWatch.

A successful run writes `artifacts/aws-verification-<run-id>.json` containing
time/account/region/model, trace IDs, request IDs and output keys. Treat a timeout,
field difference or error as a failed live check; do not label it verified.
Read logs and output JSON before retrying. Model-generated vendor/description
variations can cause strict fixture comparison to fail even if arithmetic passes.
Do not weaken the expected fixture simply to make a test pass.

This tests one synthetic invoice and document failure, not extraction accuracy
across vendors or production reliability. Outputs remain in S3 until cleanup.
The verifier scans recent output/error objects, so use a small isolated stack.

## Inspect in the AWS console

1. CloudFormation: stack resources and outputs; confirm model ID.
2. S3 input bucket: synthetic objects and version IDs under incoming/.
3. S3 output bucket: validated/ JSON containing schema_version, source, trace_id,
   request_id, and invoice fields. Decimal monetary values are strings.
4. S3 errors/: JSON containing failure stage/type, source and trace/request IDs.
5. CloudWatch > Log groups > /aws/lambda/<FunctionName>: matching trace IDs.
6. Lambda > Monitor: invocation/errors/duration; async failure destination is SQS.

For invalid date/currency/arithmetic extraction, upload examples/malformed.txt.
It is intentionally ambiguous: the actual model may emit missing fields or invalid
JSON, so inspect the resulting failure stage rather than assuming a specific one.
The automated malformed-byte check above is deterministic and avoids Bedrock cost.

## Optional controlled model-failure exercise (more charges)

Only in your disposable stack, save the working MODEL_ID, build and deploy the same
stack with `--parameter-overrides ModelId=deliberately-invalid-model-id` (keep the
changeset confirmation). IAM is updated to the invalid model too. Upload a new
valid text invoice. Expect model-stage errors, up to two asynchronous retries and
an exhausted invocation record in the failure queue. It may take minutes; inspect
Lambda asynchronous destination delivery errors if no message arrives. Actual
permissions/service failures vary, so check records rather than exact exception text.

Restore the original MODEL_ID with a reviewed SAM deployment immediately afterward.
Verify another valid invoice, or proceed to cleanup. This exercise deliberately
breaks the model configuration; never do it on a shared/production stack.

## Record confirmed results

Download evidence before closing CloudShell; /tmp is temporary. Artifacts are
ignored by Git because they include account/resource identifiers. If publishing a
portfolio screenshot or verification summary, redact account IDs and resource
names and report the actual date/model/results. Until this is run successfully,
this repository claims implementation and local testing only.
