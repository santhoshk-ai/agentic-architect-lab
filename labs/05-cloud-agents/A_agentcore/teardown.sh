#!/usr/bin/env bash
# Destroys everything Block A created. Run the same day.
set -uo pipefail
cd "$(dirname "$0")"
if [ -d NovaMcp ]; then (cd NovaMcp && agentcore remove all && agentcore deploy); fi
aws lambda delete-function --function-name nova-tools --region $REGION
aws iam detach-role-policy --role-name nova-tools-lambda-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name nova-tools-lambda-role
if [ -n "${POOL_ID:-}" ]; then   # a pool with a hosted domain (A6) can't be deleted until the domain is
  DOMAIN=$(aws cognito-idp describe-user-pool --user-pool-id $POOL_ID --region $REGION | jq -r '.UserPool.Domain // empty')
  [ -n "$DOMAIN" ] && aws cognito-idp delete-user-pool-domain --user-pool-id $POOL_ID --domain $DOMAIN --region $REGION
  aws cognito-idp delete-user-pool --user-pool-id $POOL_ID --region $REGION
fi
for LG in /aws/lambda/nova-tools $(aws logs describe-log-groups --log-group-name-prefix /aws/bedrock-agentcore/runtimes/NovaMcp_ \
    --region $REGION --query 'logGroups[].logGroupName' --output text); do
  aws logs delete-log-group --log-group-name $LG --region $REGION
done
echo "--- verify (expect empty lists) ---"
aws bedrock-agentcore-control list-gateways --region $REGION --query 'items[].name'
aws bedrock-agentcore-control list-agent-runtimes --region $REGION --query 'agentRuntimes[].agentRuntimeName'
echo "Also check ECR repos and /aws/bedrock-agentcore/* log groups the CLI created; delete if not needed."
