# Estimated cost: deploy, test, then delete

**Planning estimate, not a quote.** Currency USD, illustrative us-east-1 on-demand
rates, no free-tier credits assumed, no tax. Rates/availability were not fetched
live during implementation. Confirm current prices and model availability before
deploying, especially if using another region/model. No cost has been measured
in a real AWS run of this project.

## Small verification session

Assumptions: 20 valid invoices, each about 2,000 model input tokens (including the
prompt) and 1,000 output tokens; 256 MB Lambda averaging 10 seconds per invocation;
under 10 MB of logs and stored objects; test completed and cleaned up the same day.
Malformed-byte tests skip Bedrock. Retries/replays can multiply invocations.

| Service | Illustrative unit price | Estimate for this session |
| --- | --- | --- |
| Bedrock Nova Micro input | $0.035 / million tokens | 40,000 tokens = $0.0014 |
| Bedrock Nova Micro output | $0.14 / million tokens | 20,000 tokens = $0.0028 |
| Lambda duration, x86 | $0.0000166667 / GB-second | 20 × 10 × 0.25 = 50 GB-sec ≈ $0.00083 |
| Lambda requests | $0.20 / million | 20 requests ≈ $0.000004 |
| S3 Standard storage | $0.023 / GB-month | Less than $0.001 at this size/duration |
| S3 requests | PUT/LIST $0.005 / 1,000; GET $0.0004 / 1,000 | Usually below $0.01; verifier polling adds requests |
| CloudWatch Logs ingestion | About $0.50 / GB (standard logs) | Under $0.005 for 10 MB |
| SQS Standard | About $0.40 / million requests | Negligible for a few failed events |

**Expected planning range: about $0.01–$0.10 for a small session; set aside $1–$2
as a practical test allowance, not a spending cap.** This includes a rough allowance
for small SAM artifact storage/request usage, not every possible account charge.
One successful live verifier run sends only one invoice to Bedrock, so the raw
model cost should be lower than the 20-invoice example. Account billing rounding,
minimum storage timing and other account activity can make a bill look different.
With three attempts per invoice, the example's model cost is roughly $0.0126
instead of $0.0042. At the configured 120-second timeout, repeated slow Lambda
attempts also increase duration charges. Concurrency=2 does not cap total spend.

No EC2/NAT/database/provisioned-capacity baseline is created. Lambda/SQS have no
idle compute fee, but retained S3 versions, SAM artifacts and CloudWatch storage
continue costing money until removed. Free-tier eligibility may reduce charges;
never rely on it. Budget alerts are delayed notifications, not circuit breakers.

## Recalculate for your model and workload

```
model cost = attempts × invoices ×
  ((input_tokens × input_rate_per_million + output_tokens × output_rate_per_million) / 1,000,000)
lambda duration cost = invocations × seconds × (memory_MB / 1024) × GB_second_rate
```

Add request, storage, logs, artifact, transfer and any optional service charges.
Token count includes the system prompt; maxTokens=4096 is a response limit, not
a fixed token bill. Different Bedrock models can be substantially more expensive.
Costs quoted here assume Nova Micro on demand, not provisioned throughput,
marketplace subscriptions, inference profiles or discounted batch processing.

Check official sources:

- https://aws.amazon.com/bedrock/pricing/
- https://aws.amazon.com/lambda/pricing/
- https://aws.amazon.com/s3/pricing/
- https://aws.amazon.com/cloudwatch/pricing/
- https://aws.amazon.com/sqs/pricing/
- https://aws.amazon.com/cloudshell/pricing/
- https://calculator.aws/

Follow [cleanup](cleanup.md), then inspect your account's later billing data.
Deleting resources stops future usage/storage charges for those resources; it
cannot cancel usage already billed or unrelated resources in your account.
