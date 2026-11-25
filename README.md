# AWS Intelligent Financial Document Pipeline v0.2

Upload a synthetic invoice or receipt to S3. EventBridge starts a Standard Step Functions execution that inspects the document, claims its content in DynamoDB, extracts fields with Bedrock Nova Micro, validates them with Pydantic and Decimal arithmetic, and writes validated JSON to S3. PNG and JPEG inputs go through Textract first. Failed documents go to an SQS review queue. EventBridge target delivery failures go to a separate dead-letter queue.

**Start with the [AWS Console walkthrough](docs/DEPLOY_VERIFY_DESTROY.md).** It covers browser-only deployment using two prepared files, eight sample uploads, live evidence collection, cleanup, and billing. It also includes an optional CloudShell/SAM workflow with automation.

| Reference | Details |
| --- | --- |
| [Architecture](docs/ARCHITECTURE.md) | Event flow, state transitions, idempotency and limitations |
| [Setup](docs/SETUP.md) | Tooling, access, source and console packaging |
| [Testing](docs/TESTING.md) | Offline checks and live acceptance criteria |
| [Evidence](docs/EVIDENCE.md) | Fixture hashes and a record for actual AWS results |
| [Costs](docs/COSTS.md) | One-time estimate and pricing assumptions |
| [Runbook](docs/RUNBOOK.md) | Review, retries and operator reprocessing |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common setup and runtime problems |
| [Security](docs/SECURITY.md) | Data handling and IAM permissions |
| [Version history](CHANGELOG.md) | v0.2 changes and the [v0.1 deployment](docs/legacy-v0.1/deployment.md) |

Use a new stack name such as `finance-v02`. The original text-only pipeline and its scripts remain available with `template-v0.1.yaml`. This project uses synthetic data and has no payment execution. Live AWS results are pending until the acceptance checks run in the deployment account.
