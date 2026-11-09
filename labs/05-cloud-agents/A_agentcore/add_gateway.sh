#!/usr/bin/env bash
# Adds a CUSTOM_JWT Gateway with the Lambda target to the NovaMcp project and deploys (commands per AWS gateway quick start).
# Prereq: deploy_runtime.sh done; source setup_cognito.sh (or refresh_token.sh); export LAMBDA_ARN=...
set -euo pipefail
cd "$(dirname "$0")/NovaMcp"
# agentcore CLI 1.x: auth and Lambda target are passed as JSON. Cognito access tokens carry client_id (no aud),
# so allow by client, as deploy_runtime.sh does. toolSchemaFile is relative to the project root (NovaMcp/).
agentcore add gateway --name NovaGateway --protocol-type MCP --authorizer-type CUSTOM_JWT \
  --authorizer-configuration "{\"customJwtAuthorizer\":{\"discoveryUrl\":\"$DISCOVERY_URL\",\"allowedClients\":[\"$CLIENT_ID\"]}}"
agentcore add gateway-target --gateway NovaGateway --target-configuration \
  "{\"name\":\"NovaLambda\",\"targetType\":\"lambdaFunctionArn\",\"lambdaFunctionArn\":{\"lambdaArn\":\"$LAMBDA_ARN\",\"toolSchemaFile\":\"../tools.json\"}}"
agentcore deploy
agentcore status
echo "Copy the gateway URL (ends in /mcp) and gateway id into ../../.env as GATEWAY_URL / GATEWAY_ID"
