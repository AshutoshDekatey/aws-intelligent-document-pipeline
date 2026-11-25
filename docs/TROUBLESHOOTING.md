# Troubleshooting

| Symptom | Check |
| --- | --- |
| CloudFormation reports IAM permission or capability error | Confirm the selected account and role, acknowledge IAM creation, and request any missing CloudFormation or IAM permissions from the administrator. Inspect **Events** for the first failure. |
| CloudFormation cannot fetch Lambda code | Use the exact uploaded S3 key, same-region artifact bucket and an authorized role. Upload the inner `finance-lambda.zip` intact. |
| Lambda import fails in Pydantic | Use the Actions package or rebuild for Linux x86-64 with Python 3.12. Confirm `workflow.py`, `pydantic`, `pydantic_core` and its Linux shared library are at the ZIP root. |
| No execution after upload | Confirm the stack region, `incoming/` folder, versioned bucket, enabled EventBridge integration, and enabled rule. Allow about five minutes after first enabling integration; use an initial fresh upload after that. Check the delivery DLQ and EventBridge metrics. |
| Bedrock error | Verify Nova Micro in-region model support, the current account's access and workflow role `bedrock:InvokeModel`. A successful console playground uses your role. Compare the Lambda log to distinguish role or quota errors. |
| Valid scan goes to review | Check Textract and Bedrock request IDs and compare exact printed fields with the JSON expectations. Avoid JPEG conversion or re-encoding the supplied PNG. |
| A repeat acceptance run returns duplicates | Content IDs intentionally persist across paths. Use a fresh isolated stack for a fresh eight-case run. |
| Stack stuck in DELETE_FAILED | Stop uploads and executions, empty all versions and delete markers in both project buckets, check stack events, then retry normal deletion. |
| CloudShell unavailable | Use the browser deployment and browser evidence steps. Your organization may block both routes through IAM or SCPs. |
