# AWS Intelligent Document Pipeline — v0.1

Processes **synthetic supplier invoices** written in UTF-8 text. S3 uploads
trigger Lambda, Bedrock extracts fields, and Python validates them before
writing JSON to a separate S3 bucket. Failures produce correlated error records
and structured CloudWatch logs. This is a development baseline, not an audited
accounting system; model extraction can be plausible but wrong.

## Deploy and verify in your AWS account

The application uses **real S3, Lambda, Bedrock and CloudWatch** after deployment.
Mocked unit tests are optional development checks; they are not the application.
All deployment files, including [template.yaml](template.yaml), are committed here.

1. Read the [cost estimate](docs/costs.md) and choose a sandbox account/region.
2. Follow [AWS deployment](docs/deployment.md) in AWS CloudShell or a workstation.
3. Run [live AWS verification](docs/live-verification.md), which uploads synthetic
   documents and checks actual outputs and CloudWatch traces.
4. Follow [cleanup](docs/cleanup.md) immediately after verification.

Start here: **[AWS deployment guide](docs/deployment.md)**. No AWS resources are
created by cloning this repository, running unit tests, or GitHub Actions.
Live scripts run only when you explicitly invoke them with your account ID.
The default Bedrock model is `amazon.nova-micro-v1:0`; regional availability and
access must be confirmed before deployment. No API keys are needed in source:
Lambda uses an IAM role; CloudShell uses your signed-in AWS identity.

See [architecture](docs/architecture.md) and [v0.1 scope](docs/versions/v0.1.md).
The examples are synthetic. `expected.json` defines the fields expected by the
live test, not proof that a model has already extracted them correctly.

## Optional local developer checks

Requires Python 3.12, from the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/sam validate --lint
.venv/bin/sam build
```

Tests inject mocked clients and never authenticate to AWS. They remain useful
for regression checks but do not replace the live acceptance test. Runtime pins
are in requirements.txt and src/requirements.txt; keep both synchronized.
Transitive dependencies are resolved by pip, not fully locked.

## Data contract

Required fields: vendor, invoice_number, invoice_date, currency, line_items,
subtotal, tax, total. Each line has description, quantity, unit_price, amount.
Dates must be real calendar dates formatted YYYY-MM-DD; vendor and invoice
number must be nonblank strings. Supported two-decimal currencies: USD, EUR,
GBP, INR, CAD, AUD. Amounts must be finite, nonnegative, at most 1 billion,
and have at most two fractional digits. Quantity must be positive. Line amounts
must equal quantity × price rounded half-up to cents; subtotal must equal the
sum of lines, and total must equal subtotal + tax. No tolerance is applied.
Output money and quantities are decimal strings. Missing or extra fields fail.
No discounts, credit notes, foreign exchange, due dates, or tax-rate computation.

## Verification boundary

Local mocks verify integration wiring and validation behavior. They do not prove
AWS IAM permissions, deployment success, event delivery, regional model access,
Bedrock accuracy, latency, costs, or service quotas. No AWS deployment is
performed automatically. Deployment and live acceptance require explicit
approval and may incur charges.
