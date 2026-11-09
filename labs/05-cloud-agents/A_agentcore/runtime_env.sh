#!/usr/bin/env bash
# source runtime_env.sh -> exports AGENT_ARN and RUNTIME_URL from status_runtime.json (edit AGENT_ARN by hand if jq finds nothing)
D="$(dirname "${BASH_SOURCE[0]:-$0}")"   # zsh: BASH_SOURCE is empty, $0 is the sourced file; works from NovaMcp/ too
export AGENT_ARN=$(jq -r '..|.arn? // empty' "$D/status_runtime.json" | grep ':runtime/' | head -1)
export RUNTIME_URL="https://bedrock-agentcore.$REGION.amazonaws.com/runtimes/$(echo -n "$AGENT_ARN" | jq -sRr @uri)/invocations?qualifier=DEFAULT"
echo "AGENT_ARN=$AGENT_ARN"; echo "RUNTIME_URL=$RUNTIME_URL"
