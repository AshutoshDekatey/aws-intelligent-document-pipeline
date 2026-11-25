# Changelog

## 0.2.0 — pending live acceptance

- Added EventBridge, Standard Step Functions, Textract image OCR, Pydantic and DynamoDB deduplication.
- Added SQS review and delivery queues, bounded retries and CloudWatch alarms.
- Added browser deployment packaging, eight-case acceptance and account-checked teardown.
- Kept the v0.1 template, handler and test coverage.

## Unreleased — AWS-first deployment workflow

- Made real AWS deployment and live acceptance the primary README workflow.
- Added CloudShell setup, regional model/access prerequisites, troubleshooting,
  illustrative cost estimates, live verification and complete cleanup guides.
- Added opt-in account-checked live verification and version-aware cleanup scripts.
- Selected Amazon Nova Micro as the low-cost default direct Bedrock model.
- Added source references to error records for live event/output correlation.
- Added offline safety tests for live scripts. Real AWS execution remains unverified.

## 0.1.0 — 2026-11-04

- Added text invoice processing with S3 events, Lambda and Bedrock Converse.
- Added strict financial validation and traceable S3 error/output records.
- Added SAM infrastructure, synthetic fixtures, mocked tests and operational docs.
- AWS deployment verification is not performed as part of local implementation.
