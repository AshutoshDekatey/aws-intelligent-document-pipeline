# Testing

## Offline

From the repository root with Python 3.12, activate the environment described in [Setup](SETUP.md) and run:

```bash
export AWS_EC2_METADATA_DISABLED=true SAM_CLI_TELEMETRY=0
pytest -q
sam validate --lint
sam validate --lint --template-file template-v0.1.yaml
sam build
python scripts/package_console.py
sam validate --lint --template-file artifacts/console/finance-console.json
```

Mocks check versioned reads, metadata validation, Pydantic and money rules, Textract → Bedrock wiring, conditional claims, review handling, checkpoint reconciliation, and injected failure/recovery. v0.1 integration and operational guard tests remain. Lint checks the templates and ASL shape locally. GitHub Actions builds the browser deploy artifact without AWS credentials.

## Live acceptance

Use a fresh v0.2 stack with `EnableDemoFailures=true` and the eight uploads in [Deploy, verify and destroy](DEPLOY_VERIFY_DESTROY.md). Verify the exact amounts and fields, S3 key and version in actual workflow input, output shape/hash, DynamoDB state, AWS API request IDs for Bedrock and Textract, retry evidence and SQS review messages. The test matrix exposes extraction regressions on the supplied fixtures. It does not establish an accuracy rate on representative financial documents. Record actual results in [Evidence](EVIDENCE.md).
