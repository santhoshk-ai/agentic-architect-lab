# Results: labs/03-agent-stack

Fill in from real-provider runs (not the smoke test). Keep numbers as observed facts.

## Block 1
| Check | Bedrock (Nova 2 Lite) | Gemini |
|---|---|---|
| `llm.py` latency / tokens in / out | | |
| `triage.py` schema-valid | /5 | /5 |
| `tools_loop.py` turns, tools called | | |

Observations (structured output: forced tool vs JSON mode; injection example result):

## Block 2
| Metric | Value |
|---|---|
| Embedding model / dims | gemini-embedding-2 / 768 |
| Vector store | memory / pgvector |
| hit@3 before re-rank | /10 |
| hit@3 after re-rank (Cohere Rerank 3.5) | /10 |
| Grounding pass rate | /10 |
| Ungrounded probe blocked (scores) | |

Which questions did re-ranking fix, and why?

## Block 3
- MCP tools listed:
- Graph route per turn (memory check on turn 2):
- Interrupt → approve → reference:
- A2A task states seen:

## Architect notes
- Where would tenant identity enter this stack (MCP auth, A2A security schemes)?
- What would you log for an audit trail of every tool call?
