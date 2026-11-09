# labs/05-cloud-agents: agent platforms on AWS and Azure, LLMOps and governance

Five blocks covering managed agent platforms, multi-provider model APIs, fine-tuning, LLMOps and AI governance:

| Block | Folder | Covers | Time |
|---|---|---|---|
| A | `A_agentcore/` | Bedrock **AgentCore** Runtime + Gateway (MCP, JWT); LLMOps tracing | 1h45 |
| E1 | `E_llmops_governance/` steps 1–7 | **LLMOps**: token/cost tracking, prompt/model versioning + eval gate | 45m |
| C | `C_foundry/` | **Azure OpenAI / Foundry**; OpenAI API (Responses) | 1h |
| E2 | `E_llmops_governance/governance.md` | **Responsible AI** & AI governance (UAE AI Charter, PDPL, OWASP, NIST) | 30m |
| B | `B_bedrock_agent/` | **Bedrock Agents** (managed loop, trace, alias versioning, HITL confirmation) | 1h |
| D | `D_sagemaker/` | **SageMaker** fine-tuning (LoRA, JumpStart); needs G5 quota | 30–60m |

Each block README has: **Concept → Steps (commands + expected output) → Common errors → Done-when → Cost/teardown**.

## Setup (once)
```bash
cd agentic-architect-lab/labs/05-cloud-agents
cp .env.example .env                       # fill as you go; .env is git-ignored
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
# Block A uses its own venv (MCP SDK v1):  A_agentcore/requirements-mcp1.txt
# Block D uses its own venv (SageMaker SDK <3): D_sagemaker/requirements-sm.txt
python smoke_test.py                       # offline: compiles all, runs both Lambda handlers, usage report, gate logic, banned-term scan
```
Tools: AWS CLI v2 with creds for us-east-1, `jq`, `zip`, Node 20+ (`npm i -g @aws/agentcore`), `uv`, Azure CLI (`az login`), gcloud ADC (Gemini).

## Model choices (per AWS model cards / MS Learn)
| Use | Model | Why |
|---|---|---|
| Converse tool loops, prompt A/B | `us.amazon.nova-2-lite-v1:0` | Cheap, tool calling; **geo profile only** (no in-region) |
| Bedrock Agents | `amazon.nova-pro-v1:0` | Nova 2 Lite card lists *Agents: not supported*; Nova Pro supports Agents and runs in-region in us-east-1 (and me-central-1) |
| Foundry | deployment `gpt-5-mini` (2025-08-07, GlobalStandard, eastus) | MS Learn quickstart |
| Gemini | your labs/03 `GEMINI_MODEL`, ADC only | org policy: no API keys |

## One shared LLMOps log
Every block appends to `usage.jsonl` (git-ignored) through `common/usage.py`, using one schema: `source, model, prompt_version, input/output tokens, latency_ms, cost_usd, tools`. Set the `PRICE_*` values in `.env` from the pricing pages to get real cost. They default to 0 (cost column shows 0). `python common/usage.py` prints the cross-block table.

## Teardown checklist (after each block)
- [ ] A: `A_agentcore/teardown.sh`: no gateways or runtimes; Lambda + role + Cognito pool gone
- [ ] B: `python B_bedrock_agent/teardown_agent.py`
- [ ] C: `C_foundry/teardown_foundry.sh <rg>` → `az group exists` = false
- [ ] D: `aws sagemaker list-endpoints` = []
- [ ] E: `python E_llmops_governance/enable_invocation_logging.py --disable`

## Repo rules
Commit as yourself. Never commit `.env`, tokens, ARNs with account IDs, or `usage.jsonl`. Keep the banned term out of all files and messages (`smoke_test.py` checks this). All data is synthetic (Nova City).

## Self-check answers
**Block A**
1. **None.** The agent's JWT only lets it call the Gateway, and only until it expires. Tool credentials (Lambda role, OAuth secrets) live with the Gateway targets. Mitigations: short token lifetimes and per-client tool authorization.
2. Switch to stateful when you need elicitation (asking the user mid-call), sampling, or progress notifications.
3. The prefix keeps names unique and routable across targets. Both tools can coexist (`A___get_service_fee`, `B___get_service_fee`); what goes wrong is the *model's* choice between near-identical descriptions. Fix it with distinct descriptions or per-agent tool allow-lists / semantic tool search.

**Block E**
1. **Why git works as an audit trail:** git shows who promoted which version, when, and how the diff changed. **What a regulator still needs:** the eval dataset version, who ran the eval, environment and model version, and sign-off evidence. Store eval_results.json with dataset hash and run ID.
2. **The 1.4× cost question:** it's a business-owner decision, not an engineer's. Make the trade-off explicit: misrouted complaints carry a service and reputational cost. The gate tolerance (1.5×) encodes that pre-agreed decision.
3. **usage.jsonl vs invocation logging:** usage.jsonl is app-side (business context: source, prompt version, outcome) and only covers instrumented calls. Invocation logging is platform-side (all calls, full payloads) but has no business context. You need both, and invocation logs need privacy controls.
