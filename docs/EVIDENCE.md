# Verification evidence

Live AWS status remains **pending**. Fill in this record from the deployment account. The expected fixture values below support comparison.

| Item | Observed value |
| --- | --- |
| Date/time including timezone, region, stack, commit | Pending |
| Actual AWS services that handled inputs | Pending |
| Bedrock model ID, prompt version and request IDs | Pending |
| Textract API and scan request ID | Pending |
| Accepted JSON and DynamoDB statuses | Pending |
| Duplicate outcome and number of output versions | Pending |
| Validation failures, retry counts and SQS review messages | Pending |
| CloudWatch trace and alarm observations | Pending |
| Teardown, artifact cleanup, billing date and usage | Pending |

Keep a row per case with input S3 key and version, EventBridge event ID, Step Functions execution ARN/status, DynamoDB document ID/status, log evidence, and observed vs. expected fields. Report exact field agreement over the three expected accepted outputs and any false accepts among the rejected cases. Retain the acceptance report from `artifacts/v02-live-<run>.json` or matching console screenshots locally. Redact account IDs, unrelated resources, and console identities before publishing.

## Expected fixture IDs

The content IDs are hashes of the files as distributed. The unsupported file is rejected before content claim and is tracked under a `review#` identity derived from the source version. The duplicate reuses the valid invoice hash.

| Fixture | SHA-256 |
| --- | --- |
| `examples/invoice.txt` | `cfe8c51aeeb781deadfc30bb525682b142f71f3162448a94105a88591c3f8877` |
| `examples/malformed.txt` | `90751e9b0ab3fbd185bbbebea05192b7ed325b0edb289754c16b7a650a371b60` |
| `examples/v02/inconsistent.txt` | `ea0532ed422c692491ea588aba27be16d16281a8a1062638d494f6f6ef1c80a2` |
| `examples/v02/scanned.png` | `5a8a8bbb641bd522de29ddbab14fc78c3f7bcc3b6c41d89c497589d87693ebed` |
| `examples/v02/recoverable.txt` | `3f98e31e45a60f27942845e541d162181182b6991bfb874314e3728ed8893e97` |
| `examples/v02/exhausted.txt` | `8cbda97601532034b1c88f4c31fcf76bce9ca2b650f5d4af8446a5d2d6cbd789` |
