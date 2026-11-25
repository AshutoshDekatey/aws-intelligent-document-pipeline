# Deploy in your AWS account

This guide runs the real project in AWS. You execute it as the account owner.
Codex has not accessed your AWS account or deployed this stack. Deployment,
verification and cleanup use real APIs and may incur charges: read [costs](costs.md).
Use synthetic inputs and a sandbox account; avoid the root user.

## 1. Prepare access and region

Sign in to AWS with an authorized IAM Identity Center/IAM role. Choose
**US East (N. Virginia), us-east-1** for this walkthrough, then open **CloudShell**.
CloudShell provides temporary credentials; do not run `aws configure` or paste keys.
A local workstation with AWS CLI v2/SSO and the same tools also works.

Your deployment principal needs CloudFormation stack management, S3 bucket/object
management, Lambda management, IAM role creation/policy attachment/PassRole,
CloudWatch Logs and SQS management. The live verifier additionally reads stack
outputs/logs and reads/writes project S3 objects; cleanup deletes project objects,
versions, buckets and the stack and updates Lambda concurrency/S3 notifications.
Use an administrator-approved sandbox role; IAM/SCP/permission boundaries can
prevent deployment. The narrowly scoped Lambda role is created by SAM.

In the Bedrock console for us-east-1, check that `amazon.nova-micro-v1:0` is
available for direct on-demand Converse invocation. Complete access prerequisites
if prompted. If unavailable, stop and choose a supported **direct regional model**,
then update MODEL_ID below and recalculate costs. This template's IAM does not
support cross-region inference profiles or their ARNs.

```bash
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION="$AWS_REGION"
export STACK=invoice-v01
export MODEL_ID=amazon.nova-micro-v1:0
aws sts get-caller-identity
```

Check that the printed account is the account you intend to bill. Set the exact
12-digit account ID yourself (the scripts compare it before writes/deletions):

```bash
export EXPECTED_ACCOUNT=123456789012  # REPLACE with your own account ID
```

Keep the stack name short and lowercase: generated S3 names must fit 63 characters.
Set a small billing budget/notification in Billing if desired; budgets can lag
and are not a hard spending limit. Do not upload anything until deployment is ready.

## 2. Get every project/deployment file from GitHub

```bash
git clone --branch feat/invoice-pipeline-v0.1 \
  https://github.com/AshutoshDekatey/aws-intelligent-document-pipeline.git
cd aws-intelligent-document-pipeline
```

The feature branch is intentional until a PR is merged into main. No ZIP downloads,
manual Lambda code edits or console-created pipeline resources are needed.

CloudShell images/tool versions may change. Check Python 3.12 first:

```bash
python3.12 --version
```

If absent on an Amazon Linux 2023 CloudShell image, install it:

```bash
sudo dnf install -y python3.12 python3.12-pip
```

If that package is unavailable on your CloudShell image, use a Python 3.12
workstation; do not change the Lambda runtime just to make the build pass.
Keep tooling in temporary storage to reduce CloudShell home usage:

```bash
python3.12 -m venv /tmp/invoice-tools
source /tmp/invoice-tools/bin/activate
python -m pip install -r requirements.txt aws-sam-cli==1.145.2
export SAM_CLI_TELEMETRY=0
sam --version
```

CloudShell sessions and /tmp files are temporary; repeat tool installation after
session reset. Project source remains on GitHub. CloudShell download/build disk
space errors require freeing your own temporary files or using a workstation.
The setup uses no Docker or `sam local`.

## 3. Validate, build, review and deploy

```bash
sam validate --lint --template-file template-v0.1.yaml
sam build --template-file template-v0.1.yaml
sam deploy --guided --stack-name "$STACK" --region "$AWS_REGION" \
  --capabilities CAPABILITY_IAM --parameter-overrides ModelId="$MODEL_ID"
```

In guided setup: confirm the account, region, stack and model; allow SAM to create
the execution IAM role; keep **Confirm changes before deploy = Y** and rollback
enabled. Review the changeset before approving. SAM can create a shared managed
artifact bucket and supporting stack. It can save samconfig.toml locally; the file
is ignored because configuration is account-specific, and must contain no secrets.

The pipeline creates two encrypted private S3 buckets, Lambda + execution role,
CloudWatch log group (14 days), encrypted SQS failure queue (14 days), and S3 event
notification. There is no EC2, VPC, NAT Gateway, database or provisioned concurrency.
Reserved concurrency is 2; it is a cap, not pre-purchased capacity. Some new
accounts have insufficient Lambda concurrency quota to reserve 2: request quota
or remove that optional property in your own reviewed template before redeploying.
Concurrency caps do not limit total invocations or cost.

Capture outputs and deployment evidence:

```bash
mkdir -p artifacts
aws cloudformation describe-stacks --stack-name "$STACK" \
  --region "$AWS_REGION" > artifacts/deployed-stack.json
aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs' --output table
```

CloudFormation must show CREATE_COMPLETE/UPDATE_COMPLETE. This alone does not
verify event delivery/extraction. Continue to [live verification](live-verification.md),
then [cleanup](cleanup.md). On any failure, inspect stack events and use
[troubleshooting](troubleshooting.md); rolled-back/retained resources may still need cleanup.
