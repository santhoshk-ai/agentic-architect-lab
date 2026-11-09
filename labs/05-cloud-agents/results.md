# labs/05-cloud-agents: results

Region: us-east-1 / Azure eastus

## A: AgentCore
agentcore CLI 1.0.1, MCP server `main.py` (stateless streamable HTTP), Cognito user pool + `CUSTOM_JWT` with `allowedClients`, model `us.amazon.nova-2-lite-v1:0`. Observed, not expected.

- Runtime 401 header (no token, first lines):
  ```
  HTTP/2 401
  content-type: application/json
  x-amzn-errortype: MissingAuthenticationTokenException
  ```
  Same result on every run. No `WWW-Authenticate` header came back, unlike the README's expectation. The rejection happens at the AgentCore front door before the container sees the request, and the runtime logs show no request.
- Runtime tools/list with token: `TOOLS: ['get_service_fee', 'get_application_status']`; `CALL: get_service_fee -> {"service": "residency_renewal", "fee_ncd": 500, "source": "fee-schedule-v3 (synthetic)"}`. This matches local A1. The runtime log shows exactly 1 ListTools + 1 CallTool per run, plus about 30 PingRequest/min health checks while the session stays warm (about 15 min).
- Gateway tool names: `['NovaLambda___get_application_status', 'NovaLambda___get_service_fee']`; `CALL: NovaLambda___get_service_fee -> {"service":"residency_renewal","fee_ncd":500}`. The Lambda version has no `source` field, which shows the Gateway serves the Lambda copy of the tool, not the Runtime copy.
- gateway_agent runs (question → tools called → answer → turns), from `usage.jsonl`:
  1. Default "How much is a residency renewal, and what is the status of APP-1002?" → `get_service_fee` + `get_application_status` in parallel in turn 1 → NCD 500, APPROVED → 2 turns (1043+1182 in / 64+24 out tok, 1366 + 1170 ms)
  2. "Is APP-1003 ready, and how much is a trade licence renewal?" → both tools in parallel → NEEDS_DOCUMENTS, NCD 1200 → 2 turns (1041+1184 in / 65+24 out, 1301 + 951 ms)
  3. (fishing licence): → `get_service_fee` only → the Lambda returns `unknown service` plus the valid list, and the model says the service isn't found → 2 turns (1033+1128 in / 32+24 out, 1336 + 733 ms)
  - `python common/usage.py`: `A_gateway_agent | us.amazon.nova-2-lite-v1:0 | gw-agent-v1 | 6 calls | 6611 in | 233 out | p50 1301 ms | $0` (prices left at 0 in `.env`)
  - All 3 runs stayed well under MAX_TURNS=5. Turn 2 costs about 140 more input tokens than turn 1 because the tool results are carried in the conversation.
- A6 stretch (Runtime as mcp-server target): **blocked, not completed**. Done: M2M app client with secret + resource server `nova-mcp/invoke` + hosted domain (`setup_cognito_client_auth.sh` got an 849-char token); M2M client added to the Runtime `allowedClients` and redeployed; `agentcore add credentials oauth` (credential provider created); `add gateway-target --endpoint ... --outbound-auth oauth`.
  - The deploy failed with `GatewayTarget ... FAILED: MCP server 'https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes//invocations?qualifier=DEFAULT' returned HTTP 404 to the initialize handshake`, and the stack rolled back.
  - Root cause: `RUNTIME_URL` was empty. `runtime_env.sh` was sourced from `NovaMcp/` in zsh, where `BASH_SOURCE` is empty, so it looked for `./status_runtime.json` in the wrong folder. This is now fixed: it falls back to `$0`.
  - The Runtime logs show no Gateway-originated `initialize`/ListTools afterwards, so the Gateway → Runtime OAuth hop was never proven, and the A7 runs used only the `NovaLambda___*` tools.
  - Lesson: the Gateway validates an MCP target synchronously at create time (an initialize handshake), so a bad endpoint fails the CloudFormation deploy rather than a later tool call.
- Teardown verified: ☑ `list-gateways` and `list-agent-runtimes` are empty. Stack `AgentCore-NovaMcp-default` is gone, as are Lambda `nova-tools`, role `nova-tools-lambda-role`, and the A2–A6 user pool (with domain and M2M client).
  - `teardown.sh` now also deletes the `/aws/lambda/nova-tools` and `/aws/bedrock-agentcore/runtimes/NovaMcp_*` log groups. Re-running `setup_cognito.sh` creates a new pool each time, so delete any extra pools.
  - The ECR repo `cdk-<qualifier>-container-assets-*` belongs to the shared CDK bootstrap, so keep it.

**Gotchas hit:**
- **CDK bootstrap qualifier:** the account is bootstrapped with a custom qualifier, but the CLI-generated CDK app assumes `hnb659fds`, which causes AssumeRole AccessDenied and `SSM /cdk-bootstrap/hnb659fds/version not found`. Fix: set `@aws-cdk/core:bootstrapQualifier` in `NovaMcp/agentcore/cdk/cdk.json`. Don't re-bootstrap a shared account.
- **CLI 1.x syntax:** `add gateway` and `add gateway-target` take JSON (`--authorizer-configuration`, `--target-configuration`), and `--discovery-url` and `--type mcp-server` are gone. An MCP gateway can't take a `--runtime` target, so use `--endpoint`. OAuth secrets go into `add credentials oauth` on stdin and land in the git-ignored `agentcore/.env.local`.
- **Cognito access tokens:** these have `client_id` and no `aud`, so authorize with `allowedClients`. Client-credentials tokens need a hosted domain's `/oauth2/token` plus a resource-server scope.
- **`uv` on the Intel Mac:** `npm install uv` installs an unrelated npm package. `brew install uv` built from source (about 19 min, Tier 3 platform).

## B: Bedrock Agent
- Trace for the 2-tool question (plan / tool / result lines):
- Submit with confirm → reference ___ ; with deny → ___ ; Lambda log lines: ___
- Missing-name behaviour:
- Token overhead: B total tokens ___ vs A ___ for the same question → ratio ___
- Alias lesson (DRAFT vs v1):

## C: Foundry + 3 providers
| provider | p50 ms | in tok | out tok | intents correct (of 3) |
|---|---|---|---|---|
| Gemini | | | | |
| Nova 2 Lite | | | | |
| gpt-5-mini (Foundry) | | | | |
- Residency note: which SKU/profile would keep data in the UAE for each?

## D: SageMaker
- Quota: training ml.g5.2xlarge = ___ ; endpoint ml.g5.xlarge = ___
- Job: duration ___ s, billable ___ s, status ___  (or "Partial: quota pending")
- Holdout style match (0–4):

## E: LLMOps + governance
| version | model | acc | cost/case | p50 | p95 |
|---|---|---|---|---|---|
| triage_v1 | | | | | |
| triage_v2 | | | | | |
| triage_v3 | | | | | |
- Gate decisions: v2 ___ ; v3 ___ (reason)
- Cross-block usage table (`python common/usage.py`):
- governance.md: ✅ rows ___ / 12 ; top 3 gaps:
