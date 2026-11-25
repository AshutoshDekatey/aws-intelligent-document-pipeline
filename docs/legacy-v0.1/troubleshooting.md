# AWS troubleshooting

| Symptom | Check / next step |
| --- | --- |
| AccessDenied during deployment | Deployment role, IAM PassRole, permissions boundaries and organization SCPs. Inspect CloudFormation events. Do not broaden the Lambda role blindly. |
| Model access/validation error | Exact ModelId, regional availability, on-demand Converse support and Bedrock permissions. Direct-model IAM does not support inference profile ARNs. Restore working model after failure exercises. |
| No invocation | Upload to the stack's input bucket with lowercase incoming/ prefix and .txt suffix. Check S3 notification and Lambda resource permission. |
| No validated output | Inspect errors/ and CloudWatch trace IDs. Valid input text can still produce invalid/missing model fields. |
| Invalid invoice | Compare date, supported currency and strict Decimal arithmetic with README. PDF/binary documents are unsupported. |
| Retry/model failure | Inspect stage/type, async invocation metrics and SQS failure destination after retries exhaust. Re-upload under a new key only after remediation. |
| Live verifier times out | Check stack resources, IAM and Bedrock first. Polling does not prove the event was delivered. It requires both real outputs and logs. |
| Concurrency quota rejected | New-account regional limits may not permit reservation of 2. Request quota or review removal of the optional reservation. |
| Python build failure | Confirm Python 3.12 exists and pip can reach package repositories; build is not deployment. |
| Cleanup fails | Stop uploads; use cleanup.md manual recovery, including retained versions, failed CloudFormation resources and SAM artifacts. |

Do not place document contents, secrets or credentials in GitHub issues. Error
records intentionally omit raw exception messages; service/permission details
may require inspecting AWS service metrics and deployment events directly.
