"""
One command, no keys, no cost: proves every block is wired correctly.

    python smoke_test.py

Forces LLM_PROVIDER=mock, lexical embeddings/re-rank, local grounding check and an in-process MCP server.
Passing this means the plumbing works. It does NOT pass any Done-when; run the real providers for that.
"""
import asyncio
import os
import tempfile

os.environ.update(LLM_PROVIDER="mock", EMBED_PROVIDER="mock", RERANK="lexical", GUARDRAIL_ID="",
                  VECTOR_STORE="memory", MCP_IN_PROCESS="1")

import eval as rag_eval  # noqa: E402
import rag  # noqa: E402
import tools_loop  # noqa: E402
from llm import ask  # noqa: E402
from triage import TESTS, classify  # noqa: E402


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        raise SystemExit(1)


async def mcp_and_graph():
    from mcp import Client
    from mcp_server import mcp
    async with Client(mcp) as c:
        names = [t.name for t in (await c.list_tools()).tools]
    check("MCP lists search_faq + submit_application", {"search_faq", "submit_application"} <= set(names))

    from graph import build, turn
    g = build()
    s1 = await turn(g, "t1", "How do I renew my driving licence?")
    check("graph routes to driving specialist", s1["triage"]["service"] == "driving")
    s2 = await turn(g, "t1", "And what is the fee?")
    check("memory: follow-up stays on driving", s2["triage"]["service"] == "driving")
    s3 = await turn(g, "t1", "Please renew my driving licence now, ref LAB-009", auto_approve="yes")
    check("interrupt + approve -> SUBMITTED", (s3.get("result") or {}).get("status") == "SUBMITTED")
    s4 = await turn(g, "t2", "Please renew my driving licence now", auto_approve="no")
    check("interrupt + reject -> CANCELLED", (s4.get("result") or {}).get("status") == "CANCELLED_BY_REVIEWER")

    from starlette.testclient import TestClient
    from a2a_server import create_app
    with TestClient(create_app()) as tc:
        card = tc.get("/.well-known/agent-card.json").json()
    check("A2A agent card served", card["name"] == "Nova City Services Agent" and len(card["skills"]) == 2)


def main():
    check("llm.ask returns text", bool(ask("hello").text))
    check("triage returns schema-valid JSON x5", all(classify(m).service for m in TESTS))
    check("tool loop ends with an answer", "fee AED" in tools_loop.run("driving licence fee and slot?"))
    rag.INDEX_FILE = rag.Path(tempfile.gettempdir()) / "smoke_index.json"
    check("ingest 12 docs", rag.ingest() == 12)
    out = rag.rag("How much does it cost to renew a driving licence?")
    check("RAG cites faq-05", "faq-05" in out["citations"])
    summary = rag_eval.main(with_answers=True)
    check("ungrounded probe blocked", summary["ungrounded_probe_blocked"])
    asyncio.run(mcp_and_graph())
    print("\nSMOKE TEST PASSED - plumbing OK. Now run with real providers for the Done-when tests.")


if __name__ == "__main__":
    main()
