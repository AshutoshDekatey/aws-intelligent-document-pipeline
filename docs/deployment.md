# Deployment and cleanup

**Only execute after explicit account-owner approval for AWS access and charges.**
No command below was run against AWS during implementation. Use a disposable
sandbox and synthetic inputs. S3, Lambda, Bedrock, CloudWatch, SQS and SAM artifacts
may cost money. Concurrency limits parallel work, not total spend; establish
budgets/monitoring first.

Prerequisites: Python 3.12, README dependencies, AWS CLI v2, approved deployment
role with CloudFormation/IAM/S3/Lambda/Logs/SQS permissions, and regional Bedrock
model access. Confirm the selected direct foundation model supports Converse in
the region; obtain provider access if needed. Never put credentials in source.

```bash
export AWS_PROFILE=your-approved-sandbox-profile
export AWS_REGION=us-east-1
export STACK=invoice-v01
# Use short lowercase stack names: generated bucket name must be <=63 characters.
aws sts get-caller-identity  # verify approved account first
.venv/bin/sam validate --lint
.venv/bin/sam build
.venv/bin/sam deploy --guided --stack-name "$STACK" --region "$AWS_REGION" \
  --capabilities CAPABILITY_IAM --parameter-overrides \
  ModelId=anthropic.claude-3-haiku-20240307-v1:0
```

Review the changeset before accepting; keep confirmation enabled. SAM can create
an additional deployment-artifact bucket. Capture actual stack outputs:

```bash
aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].Outputs'
export INPUT_BUCKET=actual-InputBucketName-output
export OUTPUT_BUCKET=actual-OutputBucketName-output
export FUNCTION=actual-FunctionName-output
aws s3 cp examples/invoice.txt "s3://$INPUT_BUCKET/incoming/synthetic-001.txt"
aws s3 ls "s3://$OUTPUT_BUCKET/validated/"
aws s3 ls "s3://$OUTPUT_BUCKET/errors/" --recursive
aws logs tail "/aws/lambda/$FUNCTION" --since 10m
```

Allow asynchronous delivery. Download validated JSON, compare it to expected.json,
and inspect source version/trace/request ID. Upload malformed.txt and verify a
validation error without a validated result for that trace. A successful upload
alone proves neither extraction nor event delivery. Test controlled model failure
routing to SQS in the approved sandbox. All these live checks remain unrun.

## Cleanup (destructive; verify account and exact resource names)

Stop uploads. Record both bucket names and queue URL before stack deletion.

```bash
.venv/bin/sam delete --stack-name "$STACK" --region "$AWS_REGION"
```

Confirm Lambda, queue and logs are deleted. Buckets are retained intentionally.
In the S3 console, open the approved disposable input bucket, enable **Show
versions**, and delete every version and delete marker across all pages.
`aws s3 rm --recursive` does not remove old versions. Empty the output bucket:

```bash
aws s3 rm "s3://$OUTPUT_BUCKET" --recursive
aws s3api delete-bucket --bucket "$INPUT_BUCKET"
aws s3api delete-bucket --bucket "$OUTPUT_BUCKET"
```

Remove only this stack's unused SAM artifacts. Delete the artifact bucket only
if exclusive to this experiment and empty; preserve shared artifacts. Verify
stack deletion and removal of retained buckets/artifacts. Check billing later
because usage reports can lag.
