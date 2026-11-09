#!/usr/bin/env bash
# Deploys lambda_function.py as 'nova-tools' (Gateway Lambda target). Exports LAMBDA_ARN. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
if ! aws iam get-role --role-name nova-tools-lambda-role >/dev/null 2>&1; then
  aws iam create-role --role-name nova-tools-lambda-role --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name nova-tools-lambda-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "waiting 10s for IAM propagation..." >&2; sleep 10
fi
rm -f fn.zip && zip -q fn.zip lambda_function.py
if aws lambda get-function --function-name nova-tools --region $REGION >/dev/null 2>&1; then
  aws lambda update-function-code --function-name nova-tools --zip-file fileb://fn.zip --region $REGION >/dev/null
else
  aws lambda create-function --function-name nova-tools --runtime python3.12 --handler lambda_function.handler \
    --role arn:aws:iam::$ACCOUNT:role/nova-tools-lambda-role --zip-file fileb://fn.zip --region $REGION >/dev/null
fi
echo "export LAMBDA_ARN=arn:aws:lambda:$REGION:$ACCOUNT:function:nova-tools"
