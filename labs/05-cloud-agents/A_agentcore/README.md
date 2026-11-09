# Block A: AgentCore Runtime + Gateway (MCP), ~1h45

**CV tools covered:** Bedrock AgentCore (Runtime, Gateway, Identity/JWT); MCP in production; LLMOps (per-call usage log).

## Concept: Runtime runs code, Gateway holds the keys

| | Runtime | Gateway |
|---|---|---|
| Job | Hosts your agent or MCP server (isolated microVM per session) | One MCP front door that turns Lambdas, OpenAPI, Smithy and existing MCP servers into tools |
| MCP contract | Container listens on `0.0.0.0:8000/mcp`, streamable HTTP; stateless recommended | Endpoint `https://<id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp` |
| Inbound auth | IAM SigV4 or `CUSTOM_JWT` (discovery URL + allowed clients/audience) | `NONE` (lab only) or `CUSTOM_JWT` |
| Outbound auth | n/a | Per target: Gateway IAM role (Lambda), API key or OAuth client credentials |

**Two-hop auth is the point.** The agent holds only its JWT. The Gateway validates it, then calls each tool with that tool's own credential. A leaked agent token never exposes a tool secret, and rotating a tool key never touches agents. It works like a CDN with token auth and origin shield: players talk only to the edge, and the edge holds the origin credentials.

```
gateway_agent.py ──JWT──▶ Gateway /mcp ──IAM role──▶ Lambda nova-tools        (core path)
                              │        └──OAuth M2M──▶ Runtime MCP server /mcp  (stretch A6)
                              └─ CloudWatch /aws/bedrock-agentcore/gateways/<id>
client_check.py ──JWT──▶ Runtime /runtimes/<arn>/invocations?qualifier=DEFAULT   (direct test)
```

## Steps

```bash
cd labs/05-cloud-agents/A_agentcore
python -m venv .venv-mcp1 && source .venv-mcp1/bin/activate && pip install -r requirements-mcp1.txt
npm install -g @aws/agentcore && agentcore --version        # Node 20+ ; also needs uv and jq
export REGION=us-east-1 AWS_REGION=us-east-1 USERNAME=lab-user PASSWORD='<8+ chars, upper/lower/digit/symbol>'
```

**A1. Local MCP server (5m).** Run `python main.py`, then in a second terminal run `MCP_URL=http://localhost:8000/mcp python client_check.py`.
Expected: `TOOLS: ['get_service_fee', 'get_application_status']` and `CALL: get_service_fee -> {... "fee_ncd": 500 ...}`.

**A2. Identity (5m).** Run `source setup_cognito.sh`. It prints POOL_ID, CLIENT_ID and DISCOVERY_URL. When the token expires (about 1h), run `source refresh_token.sh`.

**A3. Runtime (20m).** Run `./deploy_runtime.sh`, then `source runtime_env.sh`. The first build takes a few minutes.

**A4. Negative test, then positive test (5m).**
```bash
curl -si -X POST "$RUNTIME_URL" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -5
#  expect: HTTP/1.1 401 ... WWW-Authenticate: Bearer resource_metadata="...oauth-protected-resource..."
MCP_URL="$RUNTIME_URL" python client_check.py          # BEARER_TOKEN already exported -> same TOOLS + CALL as local
```

**A5. Gateway with a Lambda target (25m).**
```bash
eval "$(./deploy_lambda.sh | tail -1)"                  # exports LAMBDA_ARN
./add_gateway.sh                                        # then put GATEWAY_URL / GATEWAY_ID in ../.env
export GATEWAY_URL=... GATEWAY_ID=...
MCP_URL="$GATEWAY_URL" python client_check.py
#  expect TOOLS with the target prefix, e.g. ['NovaLambda___get_application_status', 'NovaLambda___get_service_fee', ...]
```

**A6. Stretch (~20m), the interview story: Runtime MCP server as a Gateway `mcp-server` target.**
The Runtime requires a JWT, so the target needs **outbound OAuth client credentials**:
1. Create a Cognito app client *with a secret*, plus a resource server and scope: `source setup_cognito_client_auth.sh` (after `setup_cognito.sh`). It also adds the pool's hosted domain, because client-credentials tokens are only issued at its `/oauth2/token`, and exports `M2M_CLIENT_ID`, `M2M_CLIENT_SECRET`, `M2M_SCOPE` (`nova-mcp/invoke`), `TOKEN_URL` and a test `M2M_TOKEN`.
2. Add that client ID to the Runtime's `allowedClients`, then redeploy.
3. Register the M2M client as an AgentCore Identity OAuth credential, add the Runtime as an MCP endpoint target that uses it, then deploy (agentcore CLI 1.x, run in `NovaMcp/`):
```bash
printf %s "$M2M_CLIENT_SECRET" | agentcore add credentials oauth --name NovaM2M --client-id "$M2M_CLIENT_ID" \
  --discovery-url "$DISCOVERY_URL" --scopes "$M2M_SCOPE" --client-secret -      # secret -> agentcore/.env.local (git-ignored)
agentcore add gateway-target --gateway NovaGateway --name NovaMcpTarget --endpoint "$RUNTIME_URL" \
  --outbound-auth oauth --credential-name NovaM2M --scope "$M2M_SCOPE"
agentcore deploy
source ../refresh_token.sh
MCP_URL="$GATEWAY_URL" python ../client_check.py
```
Expected: `NovaMcpTarget___get_service_fee` appears next to the Lambda tools.

**A7. Agent through the Gateway + LLMOps (15m).**
```bash
python gateway_agent.py                                                     # 2 tools -> NCD 500 + APPROVED
python gateway_agent.py "Is APP-1003 ready, and how much is a trade licence renewal?"
python gateway_agent.py "What's the fee for a fishing licence?"             # tool error -> model says not found
python ../common/usage.py                                                   # per source/model/prompt_version table
aws logs tail /aws/bedrock-agentcore/gateways/$GATEWAY_ID --since 15m       # Gateway-side view
```

**A8. Teardown (10m), today:** run `./teardown.sh`. Expect both verify lists to be empty.

## Common errors
| Symptom | Cause / fix |
|---|---|
| Gateway 401 with a fresh token | Cognito **access** tokens carry `client_id`, not `aud`. If `--allowed-audience` rejects them, check `agentcore add gateway --help` for an allowed-clients option (the Runtime uses `allowedClients`). |
| 401 after ~1h | Token expired: `source refresh_token.sh` |
| 406 from Runtime | `Accept` must include `application/json, text/event-stream` |
| Lambda tool AccessDenied | Gateway role lacks `lambda:InvokeFunction`: add it with `aws lambda add-permission` for that role |
| Converse ValidationException on toolSpec | Schema keys rejected; `clean_schema()` strips `$schema`/`title`, so extend it if needed |
| `add gateway` asks for `--runtimes` | Check `agentcore add gateway --help`; the quick start attaches a gateway to an agent runtime |
| Gateway not responding right after deploy | Wait 30–60s (DNS), per AWS docs |
| A6 deploy: target `FAILED ... runtimes//invocations ... HTTP 404 to the initialize handshake` | `RUNTIME_URL` empty: run `source ../runtime_env.sh` and `echo $RUNTIME_URL` (it must contain the encoded ARN) before `add gateway-target` |
| A4 401 has no `WWW-Authenticate` header | Seen in practice: `x-amzn-errortype: MissingAuthenticationTokenException` is the same negative result |

## Done when
- [ ] A4 prints `401` + `WWW-Authenticate`, and the Runtime call with a token lists 2 tools
- [ ] A5 lists the namespaced tools through the Gateway
- [ ] A7 answers the 2-tool question in ≤ MAX_TURNS, and `usage.py` prints the table
- [ ] A8 verify lists are empty

## Self-check (answers in ../README.md)
1. Your agent's JWT leaks. Which tool credentials does the attacker hold?
2. When would you switch the MCP server to `stateless_http=False`?
3. Why does the Gateway namespace tools as `<Target>___<tool>`, and what goes wrong with two `get_service_fee` tools?

**Cost:** consumption-based (Runtime active compute, Gateway per request, Lambda per invoke). A lab this size should cost cents, but check the AgentCore pricing page.
