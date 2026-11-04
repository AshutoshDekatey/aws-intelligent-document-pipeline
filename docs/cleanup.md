# Close the AWS experiment and remove resources

Perform cleanup immediately after live verification, including after failed tests.
This is destructive. Download evidence first and stop every source of uploads.
Use the same approved account/region/stack as deployment. Cleanup stops future
project usage; it does not reverse costs already incurred or guarantee a zero bill.

## Successful deployment: opt-in cleanup script

From the repository root, with the tooling from the deployment guide:

```bash
python scripts/cleanup_aws.py --stack "$STACK" --region "$AWS_REGION" \
  --confirm-account "$EXPECTED_ACCOUNT" --delete-all-project-data
```

Before deletion it verifies account ID, project description and that both output
bucket names belong to this stack. It pauses Lambda, removes input notifications,
waits 130 seconds for in-flight work, deletes the CloudFormation stack and waits
for completion, then empties/deletes retained input/output buckets. Input **all
versions and delete markers** are deleted, not just current objects. Lambda, IAM
role, failure queue and log group should be removed by CloudFormation.

The script does not delete SAM shared infrastructure, budgets or arbitrary buckets.
If interrupted or stack deletion fails, inspect CloudFormation events and continue
manually below. Save bucket names first: after stack deletion the script cannot
rediscover them for a rerun. Do not repeatedly run it against a deleted stack.

## Manual recovery or failed deployment

1. Record the actual project bucket names, function/log group and failure queue
   using CloudFormation resources/outputs before deleting the stack. Failed builds
   create no pipeline resources; failed deployments may create some.
2. Stop uploads. For an existing Lambda, set reserved concurrency to 0. Remove
   input bucket event notifications. Wait over 120 seconds for running work.
3. Run `sam delete --stack-name "$STACK" --region "$AWS_REGION"`, reviewing prompts,
   or delete the stack in CloudFormation. Resolve DELETE_FAILED resources explicitly.
4. Retained input bucket: S3 console > Show versions > select/delete **every version
   and delete marker across every page**. `aws s3 rm --recursive` alone is insufficient.
5. Empty the retained output bucket. Delete both empty project buckets. Keep the
   exact names captured above; never select buckets merely by a similar prefix.
6. Verify Lambda, execution IAM role, project log group and queue were deleted.
   Delete project-only leftovers after confirming ownership.

## SAM artifacts and final billing check

`sam deploy --guided` can create a managed artifact bucket and a shared
`aws-sam-cli-managed-default` stack. Find the actual bucket in samconfig.toml,
SAM deployment output or that stack's outputs. Inspect it in S3:

- Delete only this experiment's artifact prefix if the bucket is shared.
- If exclusively used for this experiment, empty it (including versions if enabled)
  and remove its managed CloudFormation stack after confirming no other project
  depends on it. Never delete a shared SAM bucket or managed stack blindly.
- Delete local CloudShell artifacts/source only if no longer needed; keep GitHub
  source. Standard CloudShell has no additional compute charge, but optional VPC
  networking or other services can change costs; this guide uses standard CloudShell.
- Remove any experiment-only budget/notification if desired. Inspect Billing/Cost
  Explorer later (usage can take 24–48 hours or longer to appear). Those tools may
  have their own pricing; do not enable paid reporting just to check a tiny run.

Completion checklist: project stack deleted; invoice buckets deleted; project IAM,
Lambda, queue and log group absent; unused SAM artifacts removed; no external
uploader/replay process running. S3/log/artifact storage can continue charging if
left behind even though there is no continuously running server.
