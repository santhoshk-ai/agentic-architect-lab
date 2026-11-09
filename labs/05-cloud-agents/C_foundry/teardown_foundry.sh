#!/usr/bin/env bash
# Usage: ./teardown_foundry.sh rg-agentlab-<suffix>
set -euo pipefail
az group delete --name "$1" --yes --no-wait
echo "Deleting... check with: az group exists --name $1   (false = gone)"
echo "Note: deleted Cognitive Services accounts are soft-deleted; purge with 'az cognitiveservices account purge' if you reuse the name."
