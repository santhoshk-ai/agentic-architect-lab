# Responsible AI & governance: Nova City services agent (labs 03–05)

> Fill the **Evidence** and **Status** columns from your own runs. A row is ✅ only if you can point to a file, log or screenshot. "We intend to" is ❌.

**Frameworks mapped:** the 12 principles of the *UAE Charter for the Development and Use of AI* (UAE AI Office, 2024; principle list from u.ae); UAE PDPL (Federal Decree-Law 45 of 2021); OWASP Top 10 for LLM Applications 2025; NIST AI RMF functions (Govern / Map / Measure / Manage).

**System:** citizen-facing triage + fee/status lookup + application submission (legal effect). Synthetic data only.
**Owner:** _you_ · **Risk tier:** High (acts on behalf of citizens) · **Review date:** _yyyy-mm-dd_

| # | UAE Charter principle | Risk in this system | Control we built | Evidence (file / log) | NIST | Status |
|---|---|---|---|---|---|---|
| 1 | Strengthening human–machine ties | Citizens can't reach a human | "other"/complaint intents route to a human queue; agent says when it can't help | labs/03 triage + E/cases.json complaint cases | Map | ☐ |
| 2 | Safety | Agent loops or acts wrongly | `MAX_TURNS=5` runaway guard; tool allow-list via Gateway; errors surfaced, not guessed | A/gateway_agent.py, fishing-licence run | Manage | ☐ |
| 3 | Algorithmic bias | Worse routing for some groups or dialects | Eval set covers paraphrases; **gap:** no Arabic/dialect cases yet → add 10 Arabic cases | E/cases.json, eval_results.json | Measure | ☐ |
| 4 | Data privacy | Citizen PII in prompts and logs | Synthetic data only; invocation logs with 3-day retention; tokens never in repo; **prod:** PDPL lawful basis, KMS, PII redaction before logging | enable_invocation_logging.py, .gitignore | Govern | ☐ |
| 5 | Transparency | Citizen doesn't know it's AI, or why | Answers cite tool or source (labs/03-04 citations); disclose "AI assistant" in UI | labs/04 compare_kb results | Map | ☐ |
| 6 | Human oversight | Irreversible action without consent | `submit_application` needs confirmation (Bedrock `requireConfirmation`, LangGraph `interrupt`) | B/invoke_agent.py approve vs deny logs | Manage | ☐ |
| 7 | Governance & accountability | No one owns a change; no audit trail | Prompt/model registry + promotion gate with approver; every tool call logged (Lambda audit line, Gateway logs) | E/model_registry.json git history, CloudWatch | Govern | ☐ |
| 8 | Technological excellence | Silent quality regression | Eval gate blocks promotion if accuracy drops or cost/case > 1.5x; grounding guardrail (labs/03) | E/promote_gate.py output | Measure | ☐ |
| 9 | Human commitment (AI serves people) | Automation replaces service quality | KPI = resolution + satisfaction, not deflection; complaint path stays human | results.md KPI note | Govern | ☐ |
| 10 | Peaceful coexistence with AI | Prompt injection turns agent against users | Untrusted input in `<message>` tags; "ignore instructions in message" rule; injection eval case | E/cases.json case 9; labs/03 injection run | Manage | ☐ |
| 11 | Promoting AI awareness / inclusion | Excludes non-English or low-digital-literacy users | **gap:** Arabic first, plain-language output (D fine-tune style target), accessibility | D/data, backlog | Map | ☐ |
| 12 | Treaties & applicable laws | Data leaves the jurisdiction; licence breaches | Region and SKU choices documented (Bedrock `us.` profile, Foundry GlobalStandard = **not** UAE-resident; prod → in-region e.g. me-central-1 / sovereign cloud); Llama EULA accepted knowingly | .env.example, C/README, D/finetune_lora.py | Govern | ☐ |

## OWASP LLM Top 10 (2025) quick map
LLM01 Prompt injection → row 10 · LLM02 Sensitive info disclosure → row 4 · LLM06 Excessive agency → rows 2, 6 (allow-list + confirmation) · LLM09 Misinformation → grounding guardrail + citations (labs/03-04) · LLM10 Unbounded consumption → MAX_TURNS + usage.jsonl cost per call.

## Kill switch & budget (links to ADR-002/003)
- Disable: Gateway target removal (`agentcore remove gateway-target`), Bedrock agent alias repoint, Foundry deployment delete. Write the exact command and who may run it.
- Budget: AWS Budgets action / Azure budget alert. Record thresholds here.

## Open gaps → backlog
1. Arabic eval cases (row 3, 11) · 2. PII redaction before logging (row 4) · 3. UAE-resident hosting option per provider (row 12) · 4. Red-team set of 20 injections (row 10).
