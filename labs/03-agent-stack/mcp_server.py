"""
Block 3 - MCP server (MCP Python SDK v2, MCPServer) exposing Nova City tools over
stateless streamable HTTP at http://127.0.0.1:8000/mcp

Tools
  search_faq(query, service?)      read-only, uses the Block 2 RAG pipeline
  submit_application(...)          WRITE action - irreversible unless dry_run; callers must get human approval

Run:   python mcp_server.py           (needs `python rag.py ingest` first, else keyword fallback)
Test:  python mcp_client_check.py
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from data import FAQS

mcp = MCPServer(
    name="nova-city-services",
    instructions="Tools for the fictional Nova City Services. submit_application changes state: "
                 "only call it with dry_run=false after explicit human approval.",
    version="0.1.0",
)

SUBMISSIONS: list[dict] = []  # in-memory audit log for the lab


def _keyword_search(query: str, service: str | None, k: int = 3) -> list[dict]:
    q = set(query.lower().split())
    scored = []
    for f in FAQS:
        if service not in (None, "general") and f["service"] != service:
            continue
        overlap = len(q & set((f["title"] + " " + f["body"]).lower().split()))
        scored.append((overlap, f))
    scored.sort(key=lambda x: -x[0])
    return [dict(f, score=s) for s, f in scored[:k] if s > 0]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def search_faq(query: str, service: str | None = None) -> list[dict]:
    """Search Nova City service FAQs. service: residency | driving | general (optional filter).
    Returns up to 3 passages with id, title, body and score."""
    try:
        from rag import retrieve
        hits = retrieve(query, service=service)
        return [{"id": h["id"], "title": h["title"], "body": h["body"],
                 "score": round(h.get("rerank_score", h["score"]), 4)} for h in hits]
    except Exception as e:  # index missing or provider down -> degrade, don't fail the agent
        print(f"[search_faq] RAG unavailable ({e.__class__.__name__}: {e}); keyword fallback")
        return [{"id": h["id"], "title": h["title"], "body": h["body"], "score": h["score"]}
                for h in _keyword_search(query, service)]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def submit_application(service: str, applicant_ref: str, details: str, dry_run: bool = True) -> dict:
    """Submit a Nova City service application. Irreversible when dry_run is false:
    the caller MUST have explicit human approval first."""
    record = {
        "reference": f"NC-{uuid.uuid4().hex[:8].upper()}",
        "service": service, "applicant_ref": applicant_ref, "details": details[:300],
        "status": "DRY_RUN" if dry_run else "SUBMITTED",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if not dry_run:
        SUBMISSIONS.append(record)
    print(f"[submit_application] {record}")
    return record


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8000"))
    app = mcp.streamable_http_app(stateless_http=True, json_response=True, host=host)
    print(f"MCP server on http://{host}:{port}/mcp (stateless streamable HTTP)")
    uvicorn.run(app, host=host, port=port, log_level="warning")
