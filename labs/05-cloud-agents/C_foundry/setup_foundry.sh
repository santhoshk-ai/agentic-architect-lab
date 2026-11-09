#!/usr/bin/env bash
# Creates RG -> Foundry resource (AIServices, project management on) -> project -> gpt-5-mini deployment -> Foundry User role.
# Commands per Microsoft Learn "Quickstart: create Foundry resources".
# Usage: az login ; export SUFFIX=<your initials+digits> ; ./setup_foundry.sh
set -euo pipefail
: "${SUFFIX:?export SUFFIX=sk123 (custom domain must be globally unique)}"
RG=rg-agentlab-$SUFFIX; RES=foundry-agentlab-$SUFFIX; PROJ=agentlab; LOC=${LOC:-eastus}
az group create --name $RG --location $LOC -o none
az cognitiveservices account create --name $RES --resource-group $RG --kind AIServices --sku S0 --location $LOC \
  --custom-domain $RES --assign-identity --allow-project-management true -o none
az cognitiveservices account project create --name $RES --resource-group $RG --project-name $PROJ --location $LOC -o none
az cognitiveservices account deployment create --name $RES --resource-group $RG --deployment-name gpt-5-mini \
  --model-name gpt-5-mini --model-version "2025-08-07" --model-format OpenAI --sku-capacity 10 --sku-name GlobalStandard -o none
PROJECT_ID=$(az cognitiveservices account project show --name $RES --resource-group $RG --project-name $PROJ --query id -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --assignee-object-id $ME \
  --assignee-principal-type User --scope $PROJECT_ID -o none          # Foundry User
EP=$(az cognitiveservices account project show --name $RES --resource-group $RG --project-name $PROJ \
  --query 'properties.endpoints."AI Foundry API"' -o tsv)
echo "FOUNDRY_PROJECT_ENDPOINT=$EP   <- put in ../.env"
echo "RG=$RG  (teardown: ./teardown_foundry.sh $RG)"
echo "Role assignments can take a few minutes to apply. If first_call.py returns 401/403, wait and retry."
