# Cost worksheet

Planning estimate for **US East (N. Virginia), us-east-1** and direct on-demand **Amazon Nova Micro** as of 25 November 2026. Recheck the region selector and prices immediately before deployment. Assumes eight fixture uploads, one scanned page, up to ten Bedrock calls including repeats and a playground check, up to 150 transitions and 24 hours before deletion. Prices are in USD before tax, credits and unrelated usage.

| Service | Planning calculation | Estimate |
| --- | --- | --- |
| Bedrock | 10 calls × (1,500 input × $0.035 + 1,800 output × $0.14) / 1 million tokens | $0.00305 |
| Textract | 1 page × $0.0015 Detect Document Text | $0.00150 |
| Step Functions Standard | 150 transitions × $0.000025 | $0.00375 |
| Lambda x86 | 40 requests, up to 100 GB-s at $0.0000166667/GB-s, $0.20 per million requests | $0.00168 |
| S3 Standard | Within 30 MB for artifacts/data, about 100 PUT/LIST and 100 GET requests | About $0.001 |
| DynamoDB on demand and SQS Standard | A few dozen writes/reads, messages and polls | Below $0.001 |
| CloudWatch | Up to 10 MB logs at about $0.50/GB, three standard alarms at about $0.10/month each prorated for one day, minimal queries | About $0.016 |
| EventBridge | Native AWS service events on the default bus, no archive | $0 direct event ingestion |

This worksheet comes to roughly **$0.03** at those volumes. Allow **$0.03–$0.25** for a short sandbox session, allowing for variance and small incidental usage. Actual charges depend on the account and experiment. The near-zero idle footprint assumes teardown. Alarms and storage continue if left deployed. A budget alert is a delayed notification and cannot cap charges.

- [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) and [US East Bedrock official price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-east-1/index.json)
- [Nova Micro model card and regional access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-micro.html)
- [US East Textract official price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonTextract/current/us-east-1/index.json) and [Step Functions pricing](https://aws.amazon.com/step-functions/pricing/)
- [Lambda pricing](https://aws.amazon.com/lambda/pricing/) and [S3 pricing](https://aws.amazon.com/s3/pricing/)
- [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/), [SQS pricing](https://aws.amazon.com/sqs/pricing/) and [EventBridge pricing](https://aws.amazon.com/eventbridge/pricing/)
- [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) and [AWS Pricing Calculator](https://calculator.aws/)

Use the Lambda logs to capture actual Bedrock input/output token counts, and record OCR pages, workflow transitions and time deployed. Check **Billing → Bills** after AWS posts actual charges. This project has no measured AWS bill yet.
