# Block C: Azure OpenAI / Microsoft Foundry + three-provider interface, ~1h

**Covers:** Azure OpenAI / Azure AI Foundry; OpenAI API (Responses); multi-provider abstraction.

## Concept: same API, different control plane
- **Foundry resource** (`--kind AIServices`) is the Azure account that holds model deployments. A **project** (needs `--allow-project-management`, which you can't change later) is the workspace for agents, evals and connections.
- You call a **deployment name**, not a model ID. SKU `GlobalStandard` routes globally. For residency you'd choose a regional or DataZone SKU, so the SKU is a **data-residency decision**, the same lesson as Bedrock's `us.` vs `global.` profiles.
- **Auth = Entra ID** token (scope `https://ai.azure.com/.default`) plus the **Foundry User** role on the project. No keys, matching your org's no-API-key stance on Google.
- **Endpoint** `https://<res>.services.ai.azure.com/api/projects/<proj>/openai/v1` speaks the OpenAI Responses API. The OpenAI SDK works unchanged, which is your portability seam.
- **Data residency:** the deployment type decides where inference runs. GlobalStandard can route anywhere, so pick a regional or data-zone deployment when data must stay in-region.

## Steps
0. **Python env:** Block C uses the shared main venv, not Block A's `.venv-mcp1`. The packages come from `../requirements.txt` (`openai`, `azure-identity`, `google-genai`, `python-dotenv`, `boto3`). Azure CLI must be 2.7x or newer, because 2.2x has no `--allow-project-management` or `account project` commands.
   ```bash
   deactivate 2>/dev/null; cd ..                      # labs/05-cloud-agents
   python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
   cd C_foundry
   az version --query '"azure-cli"' -o tsv            # upgrade if < 2.70: brew upgrade azure-cli, or uv tool install azure-cli
   ```
   Error `ModuleNotFoundError: No module named 'azure'` means the wrong venv is active.
1. `az login`, then `export SUFFIX=<initials+digits>` and `./setup_foundry.sh` (~5 min). Copy `FOUNDRY_PROJECT_ENDPOINT` into `../.env`.
   - `DeploymentModelNotSupported`: the model/version/SKU isn't in the region. Try `LOC=eastus2` or check the Foundry model catalog.
   - `CustomDomainInUse`: change SUFFIX.
2. `python first_call.py`. Expected: a one-sentence answer, `status: completed`, token counts. On 401/403, wait a few minutes for the role assignment.
3. `python three_providers.py`. Expected: 9 lines (3 providers × 3 messages) with ms, tokens and parsed JSON. Intents should be driving/urgent=true, complaint, trade.
   - Run one provider with `python three_providers.py foundry`.
   - Gemini needs `gcloud auth application-default login` and `GEMINI_MODEL` from labs/03.
   - If Gemini returns an empty `r.text`, the model may be a thinking model with a low output budget: check `r.candidates`.
4. `python ../common/usage.py`: record p50 latency and tokens per provider in results.md. gpt-5-mini is a reasoning model, so expect higher output tokens (reasoning tokens are billed as output).
5. **Teardown:** `./teardown_foundry.sh rg-agentlab-<suffix>`, then `az group exists --name ...` should return `false`.

## Done when
- [ ] first_call answers with Entra ID auth (no key anywhere in the repo)
- [ ] three_providers prints 9 lines; you can explain each provider's auth model and residency control
- [ ] RG deleted

**Cost:** GlobalStandard is pay-per-token with no idle charge for the deployment, so a few cents for this lab. Check Azure pricing for gpt-5-mini.
