#!/usr/bin/env bash
set -euo pipefail

: "${STACK:?Set STACK to a dedicated short lowercase stack name}"
: "${AWS_REGION:?Set AWS_REGION}"
: "${EXPECTED_ACCOUNT:?Set EXPECTED_ACCOUNT to the approved 12-digit account}"
: "${ARTIFACT_BUCKET:?Set ARTIFACT_BUCKET to a same-region private packaging bucket}"
MODEL_ID="${MODEL_ID:-amazon.nova-micro-v1:0}"
ENABLE_DEMO_FAILURES="${ENABLE_DEMO_FAILURES:-false}"

if [[ "$(aws sts get-caller-identity --query Account --output text --region "$AWS_REGION")" != "$EXPECTED_ACCOUNT" ]]; then
    echo "Account mismatch" >&2
    exit 1
fi
aws s3api head-bucket --bucket "$ARTIFACT_BUCKET" --expected-bucket-owner "$EXPECTED_ACCOUNT" --region "$AWS_REGION"
aws bedrock get-foundation-model --model-identifier "$MODEL_ID" --region "$AWS_REGION" \
    --query 'modelDetails.{ID:modelId,Inference:inferenceTypesSupported,Lifecycle:modelLifecycle.status}'
export SAM_CLI_TELEMETRY=0
sam validate --lint
sam build
sam deploy --stack-name "$STACK" --region "$AWS_REGION" --s3-bucket "$ARTIFACT_BUCKET" \
    --s3-prefix "$STACK" --capabilities CAPABILITY_IAM --confirm-changeset \
    --parameter-overrides "ModelId=$MODEL_ID" "EnableDemoFailures=$ENABLE_DEMO_FAILURES"
