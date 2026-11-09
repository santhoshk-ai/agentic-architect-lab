#!/usr/bin/env bash
# A6 step 1: machine-to-machine (OAuth client credentials) identity for the Gateway -> Runtime hop.
# Usage: source setup_cognito.sh first (POOL_ID, REGION), then: source setup_cognito_client_auth.sh
# Adds to the existing pool: a hosted domain (client-credentials tokens are only issued at /oauth2/token),
# a resource server with one scope, and an app client WITH a secret allowed to use that scope. Safe to re-source.
# Exports M2M_CLIENT_ID, M2M_CLIENT_SECRET, M2M_SCOPE, TOKEN_URL, M2M_TOKEN.
: "${POOL_ID:?source setup_cognito.sh first}" "${REGION:?export REGION}"
RS_ID="nova-mcp"; SCOPE_NAME="invoke"
export M2M_SCOPE="$RS_ID/$SCOPE_NAME"

DOMAIN=$(aws cognito-idp describe-user-pool --user-pool-id $POOL_ID --region $REGION | jq -r '.UserPool.Domain // empty')
if [ -z "$DOMAIN" ]; then
  DOMAIN="nova-lab-$(echo "${POOL_ID#*_}" | tr '[:upper:]' '[:lower:]')"     # prefix must be unique per region
  aws cognito-idp create-user-pool-domain --user-pool-id $POOL_ID --domain $DOMAIN --region $REGION > /dev/null
fi
export TOKEN_URL="https://$DOMAIN.auth.$REGION.amazoncognito.com/oauth2/token"

if ! aws cognito-idp describe-resource-server --user-pool-id $POOL_ID --identifier $RS_ID --region $REGION > /dev/null 2>&1; then
  aws cognito-idp create-resource-server --user-pool-id $POOL_ID --identifier $RS_ID --name "Nova MCP" \
    --scopes ScopeName=$SCOPE_NAME,ScopeDescription="Call Nova MCP tools" --region $REGION > /dev/null
fi

export M2M_CLIENT_ID=$(aws cognito-idp list-user-pool-clients --user-pool-id $POOL_ID --region $REGION \
  | jq -r '.UserPoolClients[] | select(.ClientName=="nova-lab-m2m") | .ClientId' | head -1)
if [ -z "$M2M_CLIENT_ID" ]; then
  export M2M_CLIENT_ID=$(aws cognito-idp create-user-pool-client --user-pool-id $POOL_ID --client-name "nova-lab-m2m" \
    --generate-secret --allowed-o-auth-flows client_credentials --allowed-o-auth-scopes "$M2M_SCOPE" \
    --allowed-o-auth-flows-user-pool-client --region $REGION | jq -r '.UserPoolClient.ClientId')
fi
export M2M_CLIENT_SECRET=$(aws cognito-idp describe-user-pool-client --user-pool-id $POOL_ID --client-id $M2M_CLIENT_ID \
  --region $REGION | jq -r '.UserPoolClient.ClientSecret')

# Smoke test: a new domain can take ~1 min to resolve; re-source this file if the token comes back empty.
export M2M_TOKEN=$(curl -s -X POST "$TOKEN_URL" -u "$M2M_CLIENT_ID:$M2M_CLIENT_SECRET" \
  -H "Content-Type: application/x-www-form-urlencoded" -d "grant_type=client_credentials&scope=$M2M_SCOPE" | jq -r '.access_token // empty')
echo "M2M_CLIENT_ID=$M2M_CLIENT_ID"; echo "M2M_CLIENT_SECRET=<${#M2M_CLIENT_SECRET} chars, not printed>"
echo "M2M_SCOPE=$M2M_SCOPE"; echo "TOKEN_URL=$TOKEN_URL"; echo "M2M_TOKEN=<${#M2M_TOKEN} chars, ~1h lifetime>"
echo "Next (A6 step 2): add $M2M_CLIENT_ID to the Runtime's allowedClients, then agentcore deploy."
