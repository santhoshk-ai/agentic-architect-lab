# Results: labs/03-agent-stack

Fill in from real-provider runs (not the smoke test). Keep numbers as observed facts.

Run date: 2026-11-03. Bedrock `us.amazon.nova-2-lite-v1:0` (us-east-1), Gemini `gemini-3.5-flash-lite`.

## Block 1
| Check | Bedrock (Nova 2 Lite) | Gemini |
|---|---|---|
| `llm.py` latency / tokens in / out | 2056 ms / 63 / 44 | 1289 ms / 19 / 56 |
| `triage.py` schema-valid | 5/5 | 5/5 |
| `tools_loop.py` turns, tools called | 2 turns (`tool_use` → `end_turn`); `get_appointment_slots`, `get_fee` in turn 1 | 2 turns (2 function calls → 0); `get_appointment_slots`, `get_fee` in turn 1 |

Observations (structured output: forced tool vs JSON mode; injection example result):
- Bedrock gets structured output by forcing a single tool (`toolChoice`); Gemini uses JSON mode (`response_mime_type="application/json"` + schema). Both returned identical `service`/`intent`/`urgency` labels on all 5 triage messages; only the free-text `summary` wording differed.
- `lc_chain.py` (LCEL, `with_structured_output`) reproduced the same 5 labels.
- Both providers called the two tools in parallel in one turn for "When is the next driving licence renewal slot and how much does it cost?". Bedrock listed both slots; Gemini listed only the first.
- Same-prompt token counts differ a lot (system prompt in = 63 vs 19): token accounting is not comparable across providers.
- Data inconsistency: the tool fixture returns `fee_aed: 120`, the FAQ says 120 NCD.
- Injection example: not run today.

## Block 2
| Metric | Value |
|---|---|
| Embedding model / dims | gemini-embedding-2 / 768 |
| Vector store | memory |
| hit@3 before re-rank | 10/10 |
| hit@3 after re-rank (Cohere Rerank 3.5) | 10/10 |
| Grounding pass rate | 9/10 |
| Ungrounded probe blocked (scores) | Yes: `GUARDRAIL_INTERVENED`, GROUNDING 0.0, RELEVANCE 0.61 |

Which questions did re-ranking fix, and why?
- None this run: dense retrieval already put the expected FAQ at rank 1 for all 10 questions, and re-ranking kept it there. Re-ranking only reshuffled ranks 2-3 (e.g. faq-07 parking-fine question promoted faq-11 over faq-04). With a 12-document corpus and a strong embedding model, re-rank has no headroom; it earns its cost on larger, noisier corpora.
- Grounding miss: faq-06 ("I sold my car…") scored GROUNDING 0.17 although the answer only restates faq-06 with citations. Likely a guardrail false negative caused by the added unsupported closing sentence ("Ensure all requirements are met…"); grounding scores whole answers, so generic filler lowers the score.
- Per-question answer latency: 4.2-9.3 s (retrieve + re-rank + generate + guardrail).

## Block 3
- MCP tools listed: `search_faq`, `submit_application` (search_faq top hit faq-05 score 0.88; `submit_application` dry run → `DRY_RUN` reference).
- Graph route per turn (memory check on turn 2): turn 1 `driving/question` grounded (faq-05); turn 2 "And what is the fee?" `driving/question` resolved from thread memory → "120 NCD [faq-05]"; turn 3 `driving/apply` → approval interrupt. Thread held 7 history lines.
- Interrupt → approve → reference: paused with `{"service": "driving", "applicant_ref": "LAB-0012", …}`, approved → `SUBMITTED`, reference `NC-1062CDFE`. The apply-turn answer text still says "I can't confirm that from official Nova City information", because the grounding step runs on an action request; the answer node should skip it for `intent=apply`.
- A2A task states seen: `TASK_STATE_COMPLETED` (question); `TASK_STATE_INPUT_REQUIRED` → reply "no" → `TASK_STATE_COMPLETED` with `CANCELLED_BY_REVIEWER` (apply). The client needed a 120 s HTTP timeout; httpx's 5 s default timed out on a full graph run.

## Architect notes
- Where would tenant identity enter this stack (MCP auth, A2A security schemes)?
- What would you log for an audit trail of every tool call?
