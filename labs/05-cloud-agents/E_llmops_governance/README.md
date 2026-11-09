# Block E: LLMOps (tracing, token/cost, versioning) + Responsible AI governance, ~1h15

**CV tools covered:** LLMOps / MLOps (tracing, token & cost tracking, model/prompt versioning); Responsible AI & AI governance.

## Concept: treat prompts and models like deployable artifacts
```
prompts/triage_vN.txt ──▶ prompt_ab.py (eval on cases.json) ──▶ eval_results.json ──▶ promote_gate.py ──▶ model_registry.json (git = audit)
            every call ──▶ ../usage.jsonl  (source, model, prompt_version, tokens, latency, cost)  ──▶ common/usage.py report
     platform view    ──▶ Bedrock invocation logging → CloudWatch (all calls, incl. un-instrumented ones)
```
- **Tracing** answers *what happened* (Block A gateway logs, Block B agent trace, invocation logs).
- **Token and cost tracking** answers *what it cost per call / per version / per provider* (usage.jsonl).
- **Versioning plus a gate** answers *what is in production, who approved it, and on what evidence* (registry + gate). It's the same discipline as a CDN config change behind canary metrics.
- **Governance** is written evidence that controls exist (governance.md), mapped to the UAE AI Charter's 12 principles. That's the document a government panel will actually ask you about.

## Steps (main venv)
1. **Optional platform logging:** run `python enable_invocation_logging.py`. It's account-wide in us-east-1, so disable it at the end.
2. `python prompt_ab.py triage_v1 triage_v2`. Expected: v2 accuracy ≥ v1, with the likely v1 misses being complaint-about-service cases (4, 7, 12) and the injection case (9). v2 uses more input tokens because of the longer prompt; note the cost/case delta.
3. `python promote_gate.py triage_v1 --approver "<you>"` sets the baseline. It passes (it equals production) and stamps production with v1's measured accuracy and cost.
   Then `python promote_gate.py triage_v2 --approver "<you>"` should print PROMOTE or REJECT with reasons. Commit `model_registry.json`.
4. **Break it on purpose:** add a third version `triage_v3.txt` that drops the complaint rule, run `prompt_ab.py triage_v3`, then `promote_gate.py triage_v3`. Expect REJECT (accuracy drop). Screenshot it for results.md.
5. **Model A/B, same prompt:** `MODEL=us.amazon.nova-pro-v1:0 python prompt_ab.py triage_v2` (Nova Pro also has the `us.` geo profile per its model card). Compare cost/case and p50.
6. If step 1 is on: `aws logs tail /agentlab/bedrock-invocations --since 15m`. Find one prompt and its response, then `python enable_invocation_logging.py --disable`.
7. `python ../common/usage.py` gives the cross-block table (A, B, C, E). Paste it into `../results.md`.
8. **Governance (25 min):** fill the Evidence and Status columns in `governance.md` from your actual runs. Be strict: no evidence means ❌. List the gaps.

## Done when
- [ ] eval_results.json has v1, v2, v3; the gate promoted v2 (or rejected it with a reason you agree with) and rejected v3
- [ ] model_registry.json committed with history and approver
- [ ] usage table covers at least 3 sources; invocation logging disabled
- [ ] governance.md: all 12 rows have evidence or an explicit gap

## Self-check
1. Why is the git history of `model_registry.json` an audit trail, and what's missing for a regulator? (Hint: who ran the eval, on what dataset version.)
2. v2 costs 1.4× v1 per case but fixes complaint routing. Is that a promote? Who decides?
3. What's the difference between usage.jsonl and Bedrock invocation logging, and why do you need both?
