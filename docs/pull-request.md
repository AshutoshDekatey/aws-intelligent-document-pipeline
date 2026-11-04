# Add v0.1 synthetic invoice pipeline with validation and SAM infrastructure

## Change

The previously empty repository now contains an S3-triggered Python Lambda that
extracts synthetic text invoice fields through Bedrock Converse, validates dates,
currency, required fields, line items and Decimal arithmetic, and writes only
validated invoices to S3. Failures produce correlated records and safe logs.

Includes SAM infrastructure with private encrypted buckets, scoped model access,
CloudWatch retention and an async SQS failure destination; synthetic fixtures;
CI configuration; contributor, architecture, version, deployment and cleanup docs.

## Validation

35 local tests passed with mocked services, including a botocore Converse contract
stub. Dependency consistency, Python compilation and isolated local package imports passed. Initial SAM lint
accepted the template. SAM build remains unverified due to sandbox networking and
the unavailable environment guard profile; see docs/verification.md.
No AWS access, live Bedrock calls, deployment or billable resources were used.

## Review considerations

Text only, six two-decimal currencies, no discounts/credit notes. Events are at
least once; repeated model invocations can cost money and overwrite output.
Model accuracy and actual IAM/event delivery require an approved live test.
Buckets are retained; cleanup must remove input versions explicitly.

The repository had no base commit. Local main contains only an empty initialization
commit. Creating that remote base requires owner approval before this branch can
be opened as a PR. GitHub API access is also currently forbidden by the proxy.
