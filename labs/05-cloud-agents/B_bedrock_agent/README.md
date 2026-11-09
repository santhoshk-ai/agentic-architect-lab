# Block B: Bedrock Agents (managed orchestration) with trace and human approval, ~1h

**Covers:** Amazon Bedrock Agents; multi-step tool use; HITL.

## Concept: who owns the loop?

| | Your raw loop (labs/03, Block A `gateway_agent.py`) | Bedrock Agents (this block) | AgentCore Runtime |
|---|---|---|---|
| Orchestration loop | Your code | **AWS** (managed ReAct-style prompts) | Your framework code, hosted by AWS |
| Tools | Your code or MCP | Action groups (Lambda, function or OpenAPI schema), KBs | Anything, often via Gateway |
| Versioning | git | DRAFT → prepare → **alias** → immutable version | Runtime versions and endpoints |
| HITL | You build it (LangGraph `interrupt`) | `requireConfirmation` → `returnControl` | You build it |
| Pick when | Full control, portability | Fast, low-code, AWS-native, standard patterns | Custom frameworks at production scale |

**OTT analogy:** Bedrock Agents is a managed transcoding preset. You choose the ladder (instruction, tools) and AWS runs the pipeline. AgentCore is running your own encoder on managed compute.

**Model choice is a constraint, not a preference.** Nova 2 Lite's model card lists *Agents: not supported*. Nova Pro (`amazon.nova-pro-v1:0`) supports Agents and runs in-region in us-east-1, so the agent role only needs `bedrock:InvokeModel` on one model ARN (no cross-region profile permissions). Data-residency note: the same model card lists Nova Pro as **in-region in me-central-1 (UAE)**.

## Steps (main venv at lab root: `pip install -r ../requirements.txt`)

1. `python create_agent.py` (~3 min). Expected output: lambda ARN → agent role → `agent: <id>` → `prepare: PREPARED` → `alias v1: PREPARED <aliasId>` → `saved agent_state.json`.
2. **Two-tool question, read the trace:**
   `python invoke_agent.py "How much is a residency renewal, and what is the status of APP-1002?"`
   You should see `[plan]`, then `[tool] get_service_fee {'service': 'residency_renewal'}` with `[result] {"fee_ncd": 500}`, then `[tool] get_application_status ...` with `APPROVED`, `[usage]` lines, and an answer containing NCD 500 + APPROVED.
3. **Human approval (legal-effect action):**
   `python invoke_agent.py "Submit a residency renewal for Aisha Rahman" --decide ask` should print `>>> HUMAN APPROVAL NEEDED ... submit_application {...}`.
   - Answer `y`: the agent calls the Lambda and returns `APP-2xxx`.
   - Re-run with `--decide deny`: the agent should say it did not submit.
   - Verify the Lambda really ran only on confirm: `aws logs tail /aws/lambda/nova-agent-tools --since 10m`.
4. **Missing info:** `python invoke_agent.py "Submit a residency renewal"`. The agent should ask for the applicant name instead of calling the tool. That's the instruction doing its job.
5. **Versioning lesson:** edit `INSTRUCTION` in the console (or add `update_agent`), prepare, then compare `--alias TSTALIASID` (DRAFT) vs `--alias <v1 id>`. v1 keeps the old behaviour until you create alias v2. That's blue/green for agents.
6. `python ../common/usage.py`: compare `B_bedrock_agent` token totals per question with `A_gateway_agent`. The managed loop's hidden prompts are usually much larger. Write the ratio in results.md.
7. **Teardown:** `python teardown_agent.py`. The verify list should not contain `nova-city-agent`.

## Common errors
| Symptom | Fix |
|---|---|
| `create_agent` ValidationException about the role | IAM propagation: the script retries 5×10s; re-run if needed |
| `accessDeniedException` in the stream | Agent role policy must name exactly `foundation-model/amazon.nova-pro-v1:0` in the same Region. With an inference profile you'd also need the profile ARN and each destination Region's model ARN |
| `dependencyFailedException` | Lambda error or bad response shape: check `/aws/lambda/nova-agent-tools` logs |
| No `returnControl` on submit | Check the action group shows *User confirmation: Enabled* in the console. Confirmation behaviour with a Lambda executor is from AWS docs and the API shape; I haven't run it. Record what you see |
| Model not available | Confirm Nova Pro access in us-east-1 (Bedrock console → Model catalog) |

## Done when
- [ ] Trace shows 2 tool calls with correct params, and the answer has NCD 500 + APPROVED
- [ ] Submit asks for approval; confirm → reference returned and Lambda log line; deny → no Lambda call
- [ ] Token-overhead ratio (B vs A) recorded; teardown verified

**Cost:** Bedrock Agents charges for the model tokens it uses (no idle charge for the agent itself), plus Lambda invocations: cents. Check the Bedrock pricing page for Nova Pro.
