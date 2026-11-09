#!/usr/bin/env bash
# Usage: export REGION=us-east-1 USERNAME=lab-user PASSWORD='<8+ chars, upper/lower/digit/symbol>'; source setup_cognito.sh
# Adapted from the AWS "Deploy MCP servers in AgentCore Runtime" appendix. Exports POOL_ID, CLIENT_ID, BEARER_TOKEN.
export POOL_ID=$(aws cognito-idp create-user-pool --pool-name "nova-lab-pool" \
  --policies '{"PasswordPolicy":{"MinimumLength":8}}' --region $REGION | jq -r '.UserPool.Id')
export CLIENT_ID=$(aws cognito-idp create-user-pool-client --user-pool-id $POOL_ID --client-name "nova-lab-client" \
  --no-generate-secret --explicit-auth-flows "ALLOW_USER_PASSWORD_AUTH" "ALLOW_REFRESH_TOKEN_AUTH" \
  --region $REGION | jq -r '.UserPoolClient.ClientId')
aws cognito-idp admin-create-user --user-pool-id $POOL_ID --username $USERNAME --region $REGION --message-action SUPPRESS > /dev/null
aws cognito-idp admin-set-user-password --user-pool-id $POOL_ID --username $USERNAME --password "$PASSWORD" --region $REGION --permanent > /dev/null
source "$(dirname "${BASH_SOURCE[0]}")/refresh_token.sh"
export DISCOVERY_URL="https://cognito-idp.$REGION.amazonaws.com/$POOL_ID/.well-known/openid-configuration"
echo "POOL_ID=$POOL_ID"; echo "CLIENT_ID=$CLIENT_ID"; echo "DISCOVERY_URL=$DISCOVERY_URL"; echo "BEARER_TOKEN=<${#BEARER_TOKEN} chars, ~1h lifetime>"
