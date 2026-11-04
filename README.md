# AWS Intelligent Document Pipeline — v0.1

Processes **synthetic supplier invoices** written in UTF-8 text. S3 uploads
trigger Lambda, Bedrock extracts fields, and Python validates them before
writing JSON to a separate S3 bucket. Failures produce correlated error records
and structured CloudWatch logs. This is a development baseline, not an audited
accounting system; model extraction can be plausible but wrong.

## Local development (no AWS account required)

Requires Python 3.12. From the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/sam validate --lint
.venv/bin/sam build
```

Runtime dependency pins appear in `requirements.txt` and `src/requirements.txt`;
keep both synchronized. Dev tools are pinned in `requirements-dev.txt`; transitive
dependencies are resolved by pip (this is not a full dependency lock).
Tests inject mocked S3 and Bedrock clients. They never authenticate to AWS.
SAM validation/build also run locally; do not substitute `sam deploy` for them.

See [architecture](docs/architecture.md), [v0.1 scope](docs/versions/v0.1.md),
and [deployment and cleanup](docs/deployment.md). The `examples/` directory
contains a synthetic invoice, expected extracted fields, and malformed input.
Expected fields are a fixture, not evidence of actual Bedrock accuracy.

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
