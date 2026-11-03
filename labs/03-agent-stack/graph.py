"""
Block 3 - stateful multi-agent graph with LangGraph.

    START -> triage (router / supervisor)
          -> residency | driving | general   (specialist agents; each calls the MCP server for knowledge)
          -> [intent == apply] approve       (interrupt(): human-in-the-loop, graph pauses and is checkpointed)
          -> submit (MCP submit_application, dry_run=False)  |  cancelled
          -> END

Memory: InMemorySaver checkpoints state per thread_id, so a follow-up question on the same
thread ("what does it cost?") is routed using the earlier turns.

Run:
    python mcp_server.py &        # terminal 1 (or set MCP_IN_PROCESS=1 to skip the server)
    python graph.py               # scripted 3-turn demo, asks you to approve the submission
    python graph.py --auto-approve yes
"""
from __future__ import annotations

import asyncio
import json
import operator
import os
import re
import sys
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from mcp import Client

from mcp_client_check import tool_payload
from rag import answer, check_grounding, context_block
from triage import classify

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")


def mcp_target():
    if os.getenv("MCP_IN_PROCESS") == "1":
        from mcp_server import mcp
        return mcp
    return MCP_URL


async def call_tool(name: str, args: dict):
    async with Client(mcp_target()) as client:  # stateless: one short connection per call
        return tool_payload(await client.call_tool(name, args))


# ---------------------------------------------------------------- state
class State(TypedDict, total=False):
    question: str
    history: Annotated[list[str], operator.add]   # reducer: appended across turns (memory)
    triage: dict
    sources: list[dict]
    answer: str
    grounding: dict
    pending: dict | None
    decision: str | None
    result: dict | None


# ---------------------------------------------------------------- nodes
async def triage_node(state: State) -> dict:
    t = classify(state["question"], state.get("history"))
    return {"triage": t.model_dump(), "pending": None, "decision": None, "result": None}


PERSONAS = {
    "residency": "You are the Nova City residency desk agent.",
    "driving": "You are the Nova City driving and vehicles desk agent.",
    "general": "You are the Nova City general enquiries agent.",
}


def make_specialist(service: str):
    async def specialist(state: State) -> dict:
        q = state["question"]
        hits = await call_tool("search_faq", {"query": q, "service": service}) or []
        out = answer(q, hits, persona=PERSONAS[service])
        g = check_grounding(q, context_block(hits), out["answer"])
        text = out["answer"] if g["grounded"] else \
            "I can't confirm that from official Nova City information. Please contact a service centre."
        pending = None
        if state["triage"]["intent"] == "apply":
            ref = re.search(r"\bref\s+([A-Za-z0-9-]+)", q)
            pending = {"service": service, "applicant_ref": ref.group(1) if ref else "LAB-001",
                       "details": state["triage"]["summary"]}
        return {"sources": hits, "answer": text, "grounding": g, "pending": pending,
                "history": [f"user: {q}", f"assistant[{service}]: {text}"]}
    specialist.__name__ = service
    return specialist


async def approve_node(state: State) -> dict:
    decision = interrupt({"type": "approval", "action": "submit_application",
                          "args": state["pending"], "prompt": "Approve this submission? (yes/no)"})
    approved = str(decision).strip().lower() in {"y", "yes", "approve", "approved"}
    return {"decision": "approved" if approved else "rejected"}


async def submit_node(state: State) -> dict:
    record = await call_tool("submit_application", {**state["pending"], "dry_run": False})
    return {"result": record, "history": [f"system: submitted {record.get('reference')}"]}


async def cancelled_node(state: State) -> dict:
    return {"result": {"status": "CANCELLED_BY_REVIEWER"}, "history": ["system: submission rejected"]}


# ---------------------------------------------------------------- graph
def build(checkpointer=None):
    g = StateGraph(State)
    g.add_node("triage", triage_node)
    for s in ("residency", "driving", "general"):
        g.add_node(s, make_specialist(s))
    g.add_node("approve", approve_node)
    g.add_node("submit", submit_node)
    g.add_node("cancelled", cancelled_node)

    g.add_edge(START, "triage")
    g.add_conditional_edges("triage", lambda s: s["triage"]["service"],
                            {"residency": "residency", "driving": "driving", "general": "general"})
    for s in ("residency", "driving", "general"):
        g.add_conditional_edges(s, lambda st: "approve" if st.get("pending") else END,
                                {"approve": "approve", END: END})
    g.add_conditional_edges("approve", lambda s: "submit" if s["decision"] == "approved" else "cancelled",
                            {"submit": "submit", "cancelled": "cancelled"})
    g.add_edge("submit", END)
    g.add_edge("cancelled", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


async def turn(graph, thread_id: str, question: str, auto_approve: str | None = None) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}}
    state = await graph.ainvoke({"question": question}, cfg)
    if "__interrupt__" in state:
        req = state["__interrupt__"][0].value
        print(f"\n  ⏸  PAUSED for human approval: {json.dumps(req['args'])}")
        decision = auto_approve if auto_approve is not None else input(f"  {req['prompt']} ")
        state = await graph.ainvoke(Command(resume=decision), cfg)
    return state


DEMO = [
    "How do I renew my driving licence?",
    "And what is the fee?",                                      # follow-up: memory keeps it on 'driving'
    "Please renew my driving licence now, ref LAB-0012",          # intent=apply -> interrupt
]


async def main():
    auto = None
    if "--auto-approve" in sys.argv:
        auto = sys.argv[sys.argv.index("--auto-approve") + 1]
    graph = build()
    open("graph.mmd", "w").write(graph.get_graph().draw_mermaid())
    for q in DEMO:
        s = await turn(graph, "citizen-1", q, auto)
        print(f"\nQ: {q}\n  route={s['triage']['service']} intent={s['triage']['intent']} "
              f"grounded={s['grounding']['grounded']} sources={[h['id'] for h in s['sources']]}")
        print(f"  A: {s['answer']}")
        if s.get("result"):
            print(f"  RESULT: {s['result']}")
    print(f"\nmemory (thread citizen-1): {len(s['history'])} history lines; graph diagram -> graph.mmd")


if __name__ == "__main__":
    asyncio.run(main())
