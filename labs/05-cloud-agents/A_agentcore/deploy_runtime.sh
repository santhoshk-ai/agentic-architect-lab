#!/usr/bin/env bash
# Deploy main.py as an MCP server on AgentCore Runtime with CUSTOM_JWT inbound auth (commands per AWS runtime-mcp doc).
# Prereq: source setup_cognito.sh ; npm install -g @aws/agentcore ; uv installed
set -euo pipefail
cd "$(dirname "$0")"
agentcore create --name NovaMcp --template empty
cd NovaMcp
agentcore add runtime --name NovaTools --language python --protocol MCP \
  --authorizer-type CUSTOM_JWT \
  --authorizer-configuration "{\"customJwtAuthorizer\":{\"discoveryUrl\":\"$DISCOVERY_URL\",\"allowedClients\":[\"$CLIENT_ID\"${M2M_CLIENT_ID:+, \"$M2M_CLIENT_ID\"}]}}" \
  --request-header-allowlist Authorization
cp ../main.py app/NovaTools/main.py
(cd app/NovaTools && uv init --bare && uv add "aws-opentelemetry-distro~=0.21.0" "mcp>=1.28.1,<2")
agentcore build
agentcore deploy
agentcore status --json > ../status_runtime.json
echo "Saved status to status_runtime.json. Now: source ../runtime_env.sh"
  