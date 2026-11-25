# Deploy, verify and destroy

## 1. Sign in and check access

1. Open the [AWS Management Console](https://console.aws.amazon.com/) and sign into the sandbox account through your authorized role or IAM Identity Center. Compare the account ID in the upper-right menu with the one you intend to use. Select **US East (N. Virginia)**. Confirm you have the permissions described in [Setup](SETUP.md).
2. Open **Amazon Bedrock → Model catalog**, find **Amazon Nova Micro**, and check the model ID `amazon.nova-micro-v1:0` and in-region on-demand support. Resolve any account access prompts. If you want to test your identity before deployment, open **Chat/Text playground**, select the direct model if offered, and send one synthetic short prompt such as “Reply with OK.” That is a billable inference and checks the operator identity. The first pipeline run checks the different Lambda role. Do not create provisioned throughput, a cross-region profile, or a permanent API key.
3. Review the [cost worksheet](COSTS.md) and decide before creating anything. Prepare to keep this stack only for the verification session. Budget alerts are delayed and do not cap spending.

## 2. Deploy in the browser

1. Download the repository and the prepared console artifact per [Setup](SETUP.md). Extract each outer ZIP. Keep `finance-lambda.zip` zipped. You need the generated `finance-console.json`, `finance-lambda.zip`, and the local `examples/` folder.
2. Go to **S3 → General purpose buckets → Create bucket**. Choose a globally unique name in the same region, such as `finance-v02-artifacts-<unique-suffix>`. Keep **Block all public access**, default S3-managed encryption, and versioning disabled for this small packaging bucket. Create it and upload `finance-lambda.zip` at the root. Record its name and exact object key. This bucket is separate from the two pipeline buckets.
3. Go to **CloudFormation → Stacks → Create stack → With new resources (standard)**. Choose **Template is ready → Upload a template file**, select `finance-console.json`, and choose **Next**. If the console asks for permission to stage the template, allow the console's CloudFormation S3 upload or upload the JSON beside the ZIP and use its S3 object URL as the template source. Record the exact staging location for cleanup.
4. Use stack name `finance-v02` or another dedicated name starting with a letter and at most 32 characters. Enter **CodeBucket** as the artifact bucket name, **CodeKey** as `finance-lambda.zip`, **ModelId** as `amazon.nova-micro-v1:0`, and **EnableDemoFailures** as `true` for the eight-upload test. Keep rollback enabled and use only an approved role. Proceed to the review screen, acknowledge creation of IAM resources, and submit.
5. Wait for **CREATE_COMPLETE**. On failure, read **Events** from the first failed resource and follow [Troubleshooting](TROUBLESHOOTING.md). Save the stack's **Outputs** and **Resources** lists. CloudFormation provisions two versioned buckets, one Lambda and role, one Standard state machine and role, an EventBridge upload rule and role, a DynamoDB table, two SQS queues and a queue policy, a three-day Lambda log group, and three CloudWatch alarms.
6. Allow roughly five minutes for S3's EventBridge notification configuration to take effect before the first upload. Confirm **S3 → input bucket → Properties → Event notifications → Amazon EventBridge** is on and the rule shown by `UploadRuleName` is enabled.

## 3. Upload eight fixtures and verify in the browser

Use the **input** bucket in the stack's **Outputs** tab. In S3 create the `incoming` folder, open it, and choose **Upload → Add files**. Use the target keys in the table, retaining each filename. Create and enter `duplicate` inside `incoming` for the second upload. Wait for the first invoice to be accepted before uploading the duplicate. Do not edit the contents. Empty folder-marker executions terminate at FolderMarker and create no rows or review messages. Upload the other six cases once each. Keep version IDs from **S3 → Objects → Show versions**.

| Case | Local file | Target key | Expected execution and evidence |
| --- | --- | --- | --- |
| Valid | `examples/invoice.txt` | `incoming/invoice.txt` | SUCCEEDED, `ACCEPTED`, Bedrock request ID, total `34.10` |
| Byte-identical duplicate | same `invoice.txt` | `incoming/duplicate/invoice.txt` | SUCCEEDED, `DUPLICATE_ACCEPTED`, original owner and one output version |
| Invalid invoice | `examples/malformed.txt` | `incoming/malformed.txt` | FAILED, `ReviewRequired`, `INVALID_EXTRACTION` |
| Inconsistent total | `examples/v02/inconsistent.txt` | `incoming/inconsistent.txt` | FAILED with review, `INVALID_EXTRACTION`, no accepted output |
| Unsupported | `examples/v02/unsupported.csv` | `incoming/unsupported.csv` | FAILED with review, `UNSUPPORTED_FORMAT`, no Bedrock call |
| Scan | `examples/v02/scanned.png` | `incoming/scanned.png` | SUCCEEDED, `ACCEPTED`, Textract and Bedrock request IDs, invoice `SYN-2026-002` |
| Recoverable | `examples/v02/recoverable.txt` | `incoming/recoverable.txt` | SUCCEEDED, `ACCEPTED`, one injected error, invoice `SYN-2026-003` |
| Attempts exhausted | `examples/v02/exhausted.txt` | `incoming/exhausted.txt` | FAILED with review after three injected attempts |

1. **Step Functions → State machines → your workflow → Executions**. Open each execution. Match `detail.bucket.name`, `detail.object.key`, and `detail.object.version-id` in the execution input with the upload. Capture execution ARN, input EventBridge event ID, status, result, and relevant graph/history. Check that the duplicate bypasses extraction and that recovery shows a retry of **ExtractAndValidate**.
2. **S3 → output bucket → validated/**. Open each accepted JSON or download it. Compare the invoice number, date, vendor, currency, all line items and amounts against [examples/expected.json](../examples/expected.json), using the invoice-number variants above. Expect three output keys on a fresh stack and a single version per key. Each JSON contains the SHA-256 document ID, source version, model ID, prompt version and execution ID.
3. **DynamoDB → Explore items → table named by DocumentsTable**. Use **Scan** on the small demo table. Verify three ACCEPTED rows with output keys and four REVIEW_REQUIRED rows. The unsupported input has a separate `review#` ID. Check duplicate ownership against the first upload. Use the [fixture hashes](EVIDENCE.md) to match the content records.
4. **CloudWatch → Logs → Log groups → ProcessorLogGroupName**. Open Logs Insights on that group and use the query below. Replace the placeholder with the execution ARN. Look for `bedrock_completed` with the model and request ID, `textract_completed` with its request ID for the scan, `injected_transient` and review/task error logs. Logs can arrive after execution completion.
5. **SQS → queue named in ReviewQueueUrl → Send and receive messages → Poll for messages**. Capture four distinct reviewed execution IDs with source version and classification. Standard SQS can redeliver messages. Confirm no unexpected delivery-failure messages in the other queue. EventBridge delivery DLQ behavior itself is provisioned and monitored but this acceptance suite exercises the workflow review queue, not a deliberate EventBridge permission break.
6. Capture actual results using [Evidence](EVIDENCE.md) before teardown. Include any discrepancy from the table. A model that rewrites an inconsistent invoice rather than copying it fails the acceptance check if the bad invoice is accepted.

```sql
fields @timestamp, @message
| filter @message like /REPLACE_WITH_EXECUTION_ARN/
| sort @timestamp asc
```

## 4. Destroy in the browser

1. Save evidence and record the names of both buckets, rule, state machine, function, DynamoDB table, roles, queues, log group, alarms, and any artifact/staging bucket from **CloudFormation → Resources** and **Outputs**. Stop all uploads and manual executions.
2. **EventBridge → Rules → default event bus → your upload rule → Disable**. Allow the five-minute maximum EventBridge retry age to elapse. Then confirm no executions are **Running** in Step Functions. Allow active executions to finish, or stop them and wait at least 100 seconds for any already-running Lambda task to exit before emptying buckets.
3. **S3 → General purpose buckets → each of the two pipeline buckets → Empty**. Enter the confirmation when prompted. **Empty** removes current objects, prior versions and delete markers. Check both buckets with **Show versions**. Leave the empty buckets for CloudFormation to delete.
4. **CloudFormation → Stacks → finance-v02 → Delete**. Confirm and wait for **DELETE_COMPLETE**. Use **Events** to resolve any **DELETE_FAILED** resource and retry deletion. If stack creation failed partway, first inventory resources from the stack's **Resources** tab. Disable/drain any existing rule/workflow, empty any project buckets created, then delete the partial stack and check its resource list.
5. Verify both S3 buckets, the EventBridge rule, state machine, Lambda, DynamoDB table, both queues, log group, alarms and stack roles are absent using the names you recorded. Separately delete the uploaded ZIP and any generated template object. Empty and delete a dedicated artifact bucket you created for this project. If the console staged the JSON in a shared bucket, remove only this stack's identified template object or owned prefix. Keep shared packaging infrastructure and unrelated objects.
6. Open **Billing and Cost Management → Bills**. Check the current month and service/region line items after usage posts, typically after a day or two. If Cost Explorer is already enabled, filter by experiment dates/region and services. Account totals can include credits, taxes and unrelated workloads. Record observed charges in your evidence. Removing resources stops their future usage and storage charges.

## Optional CloudShell and SAM deployment

Use this route if CloudShell is allowed. It supplies temporary credentials for the current sign-in. Open **CloudShell** via the terminal icon in the AWS Console header in N. Virginia. If CloudShell or its AWS permissions are restricted, use Sections 1–4.

```bash
aws --version
git --version
python3.12 --version
# If Python 3.12 is absent on Amazon Linux 2023 and sudo is available:
# sudo dnf install -y python3.12 python3.12-pip
git clone --branch feat/financial-pipeline-v0.2 https://github.com/AshutoshDekatey/aws-intelligent-document-pipeline.git
cd aws-intelligent-document-pipeline
python3.12 -m venv /tmp/finance-v02-tools
source /tmp/finance-v02-tools/bin/activate
python -m pip install -r requirements-dev.txt
sam --version

export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
export STACK=finance-v02 MODEL_ID=amazon.nova-micro-v1:0 ENABLE_DEMO_FAILURES=true
aws sts get-caller-identity
export EXPECTED_ACCOUNT=REPLACE_WITH_CONFIRMED_ACCOUNT_ID
export ARTIFACT_BUCKET=REPLACE_WITH_PRIVATE_SAME_REGION_BUCKET
./scripts/deploy_v02.sh
```

Create the artifact bucket as in Section 2 before running the script. The script checks account and catalog details, builds the package, stages assets under the stack prefix, then presents a CloudFormation change set. Review and approve when ready. The deployment command it executes is:

```bash
sam deploy --stack-name "$STACK" --region "$AWS_REGION" --s3-bucket "$ARTIFACT_BUCKET" \
  --s3-prefix "$STACK" --capabilities CAPABILITY_IAM --confirm-changeset \
  --parameter-overrides "ModelId=$MODEL_ID" "EnableDemoFailures=$ENABLE_DEMO_FAILURES"
```

Run the verifier **instead of** manually uploading the fixtures. Use a fresh stack. Download the evidence and manifest via CloudShell **Actions → Download file** before the session closes.

```bash
aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].Outputs' --output table
# Allow five minutes from stack creation for EventBridge notification propagation.
python scripts/accept_v02.py --stack "$STACK" --region "$AWS_REGION" \
  --confirm-account "$EXPECTED_ACCOUNT" --run-live
# After saving evidence and stopping uploads and manual execution starts:
python scripts/destroy_v02.py --stack "$STACK" --region "$AWS_REGION" \
  --confirm-account "$EXPECTED_ACCOUNT" --delete-all-project-data
# Optional repeat verification using the saved resource inventory:
python scripts/destroy_v02.py --stack "$STACK" --region "$AWS_REGION" \
  --confirm-account "$EXPECTED_ACCOUNT" --verify-only
```

The cleanup script drains the workflow, empties the stack buckets, deletes the stack and verifies inventoried resources. Finish by removing the separate artifact bucket or the owned prefix and checking Billing as in Section 4. If permissions or a partial deployment prevent scripted teardown, use the browser recovery steps in Section 4.
