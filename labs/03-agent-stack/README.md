# labs/03-agent-stack: from one LLM call to a multi-agent service

A small **Nova City Services** assistant (a fictional city) built up in three blocks, one per day. Each block adds a layer an agent platform needs in production.

```
citizen / other agent
   │  A2A (agent card + JSON-RPC)                         ← Block 3
   ▼
LangGraph: triage ─▶ residency | driving | general ─▶ approve (interrupt) ─▶ submit
   │                     │  MCP (streamable HTTP)                            ← Block 3
   │                     ▼
   │               MCP server: search_faq │ submit_application
   │                     │
   │                     ▼
   │               RAG: embed → vector top-8 → re-rank top-3 → cited answer → grounding guardrail   ← Block 2
   ▼
llm.py ask()/ask_json(): Bedrock Converse (Nova 2 Lite) | Gemini | mock                            ← Block 1
```

| Block | Files | CV tools covered |
|---|---|---|
| 1 · Models, prompts, tools | `llm.py`, `triage.py`, `tools_loop.py` | Python for AI services · LLM APIs · prompt engineering · tool calling |
| 2 · Retrieval and evaluation | `data.py`, `rag.py`, `eval.py`, `setup_guardrail.py`, `docker-compose.yml` | embeddings · vector DB (pgvector) · RAG · guardrails and evals |
| 3 · Agents and protocols | `mcp_server.py`, `mcp_client_check.py`, `graph.py`, `lc_chain.py`, `a2a_server.py`, `a2a_client.py`, `agent-card.json` | MCP · LangGraph/LangChain · multi-agent · A2A |

## 0 · Setup (10 min)

```bash
cd labs/03-agent-stack
python3 -m venv .venv && source .venv/bin/activate      # Python 3.11+
pip install -r requirements.txt
cp .env.example .env                                     # fill in GEMINI_API_KEY; AWS creds via your profile
python smoke_test.py                                     # offline, no keys, no cost: every line should say PASS
```

`smoke_test.py` uses a deterministic mock model, so it proves the wiring works without a single API call. **It does not count as a Done-when.** For those, run the real providers below.

**AWS prerequisites:**
- Bedrock model access in `us-east-1` for **Amazon Nova 2 Lite** and **Cohere Rerank 3.5** (console → Bedrock → Model access).
- Nova is called through the `us.` inference profile.

---

## Block 1 · Models, prompts and tools (Mon, ~75 min)

```bash
COMPARE=bedrock,gemini python llm.py "In two sentences, what is a context window?"
python triage.py                     # LLM_PROVIDER=bedrock, then repeat with LLM_PROVIDER=gemini
python tools_loop.py                 # raw tool loop; watch stopReason=tool_use → end_turn
LLM_PROVIDER=gemini python tools_loop.py
```

**What to notice:**
- `ask_json` gets structured output two different ways:
  - Bedrock: a **forced tool call** whose input schema is the pydantic model.
  - Gemini: native **JSON mode** with `response_schema`.
- `triage.py` wraps citizen text in `<message>` tags and includes an injection example, so an instruction inside the message is classified, not obeyed.
- `MAX_TURNS` and the tool allow-list live in *our* code, not in the prompt.

**Done when:**
- The same prompt is answered by Bedrock and Gemini through `ask()`.
- `triage.py` prints **5/5 schema-valid** on both providers.
- `tools_loop.py` calls both tools and finishes in under 5 turns.

---

## Block 2 · RAG and evaluation (Tue, ~75 min)

```bash
python setup_guardrail.py            # once → copy GUARDRAIL_ID into .env
python rag.py ingest                 # 12 FAQs → gemini-embedding-2 (768d) → vector store
python rag.py ask "Can I bring my mother to live with me on my residency?"
python eval.py                       # hit@3 before/after re-rank, grounding pass rate, ungrounded probe
```

**Optional pgvector run** (Docker):

```bash
docker compose up -d
VECTOR_STORE=pgvector python rag.py ingest && VECTOR_STORE=pgvector python eval.py
```

This creates an HNSW index with `vector_cosine_ops` and filters `WHERE service = …` in SQL.

**What to notice:**
- Embedding 2 takes the task as a **text prefix**: `task: question answering | query: …` and `title: … | text: …`. It does not use `task_type`.
- Each text is embedded in its own call, because a list in one call is aggregated into a single vector.
- Compare `vector_top3` and `rerank_top3` in `eval_results.json`. Re-ranking fixes the paraphrased questions.
- The ungrounded probe is a fabricated answer. The guardrail must return `GUARDRAIL_INTERVENED`.

**Done when:** `eval.py` prints `DONE-WHEN: PASS`. That means hit@3 after re-rank is at least 8/10 and the ungrounded probe was blocked, using real embeddings.

---

## Block 3 · MCP, LangGraph, A2A (Wed, ~90 min)

```bash
# terminal 1
python mcp_server.py                 # stateless streamable HTTP on http://127.0.0.1:8000/mcp
# terminal 2
python mcp_client_check.py           # lists tools, calls search_faq + submit_application(dry_run)
python graph.py                      # 3-turn demo; approve the submission when it pauses
python lc_chain.py                   # same triage as an LCEL chain (prompt | model.with_structured_output)
# terminal 3
python a2a_server.py                 # agent card at http://127.0.0.1:9999/.well-known/agent-card.json
# terminal 2
python a2a_client.py                 # another agent discovers it, asks, gets INPUT_REQUIRED, approves
```

To skip terminal 1, set `MCP_IN_PROCESS=1`: the graph then talks to the MCP server object in memory.

**What to notice:**
- `graph.mmd` shows the topology (paste it into any Mermaid viewer).
- **Memory:** turn 2 ("And what is the fee?") has no service keyword, yet routes to *driving*. The checkpointed `history` for `thread_id=citizen-1` carries it.
- **Human-in-the-loop:** `interrupt()` pauses and checkpoints the graph. `Command(resume="yes")` continues it. Nothing irreversible happens without approval.
- **MCP vs A2A:** MCP is agent→tool (the server exposes functions). A2A is agent→agent (an opaque peer with its own state and a task lifecycle). The approval pause surfaces to the remote agent as `TASK_STATE_INPUT_REQUIRED`.

**Done when:** `graph.py` routes correctly, keeps memory across turns, and pauses before `submit_application`. `a2a_client.py` completes the approve flow and ends in `TASK_STATE_COMPLETED`.

---

## Cost and teardown

- **Cost:** tokens only. A full run of all blocks is a few hundred small calls. Check the Bedrock and Gemini pricing pages if you want exact figures, and record them in `results.md`.
- **Guardrail:** `python setup_guardrail.py delete`
- **pgvector:** `docker compose down -v`

## Known gaps / verify on your machine

- The pgvector path was written against pgvector 0.8 SQL but **not executed** in the build environment (no Docker daemon). The memory store path was run and passes.
- Cohere Rerank 3.5 on Bedrock is Region-limited. If `us-east-1` rejects the model ARN, set `RERANK_MODEL_ARN` to the `us-west-2` ARN with `AWS_REGION=us-west-2`, or run `RERANK=lexical` to continue.
- A2A uses `a2a-sdk` 1.3.0 (protocol 1.0, JSON-RPC binding). Older 0.3 clients use the `message/send` method name, while 1.0 uses `SendMessage`.
