# Setup

Use an authorized AWS sandbox role and verify the account and selected region before resource creation. Ask the account administrator for CloudFormation stack and change-set operations, IAM role creation and PassRole, EventBridge, Step Functions, Lambda, S3, CloudWatch, DynamoDB and SQS provisioning access. Verification needs S3 upload/read/version listing, Step Functions execution and history reads, DynamoDB reads, SQS receive, and CloudWatch Logs reads. Teardown needs permission to disable the rule, empty versioned buckets and delete stack resources. CloudShell permissions are required only for the optional shell path.

Use **US East (N. Virginia), us-east-1** with **Amazon Nova Micro** `amazon.nova-micro-v1:0` direct on-demand. Verify catalog access and estimate costs using the [deployment guide](DEPLOY_VERIFY_DESTROY.md) and [cost worksheet](COSTS.md).

## Source and artifacts

Open the [v0.2 branch on GitHub](https://github.com/AshutoshDekatey/aws-intelligent-document-pipeline/tree/feat/financial-pipeline-v0.2) and use **Code → Download ZIP** for examples and documentation. Download the separate **finance-console** artifact from the successful [offline verification workflow](https://github.com/AshutoshDekatey/aws-intelligent-document-pipeline/actions/workflows/test.yml) for the same commit. Sign into GitHub to download Actions artifacts. Extract it and keep `finance-lambda.zip` compressed. `finance-console.json` is the generated SAM template that refers to the ZIP via `CodeBucket` and `CodeKey` parameters.

Regenerate the artifact with Python 3.12 and Git on Linux x86-64, or use the CloudShell setup documented in the deployment guide.

```bash
git clone --branch feat/financial-pipeline-v0.2 https://github.com/AshutoshDekatey/aws-intelligent-document-pipeline.git
cd aws-intelligent-document-pipeline
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
export SAM_CLI_TELEMETRY=0 AWS_EC2_METADATA_DISABLED=true
sam build
python scripts/package_console.py
sam validate --lint --template-file artifacts/console/finance-console.json
```

Use an x86-64 Lambda-compatible build for Pydantic's compiled extension. For a containerized build, use Docker and `sam build --use-container`. The browser deployment uses only the packaged files, and requires IAM authorization in the AWS Console.
