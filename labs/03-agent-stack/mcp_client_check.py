"""
Block 3 - check the MCP server like any MCP client would: list tools, call them.

    python mcp_client_check.py                  # http://127.0.0.1:8000/mcp (server running)
    python mcp_client_check.py --in-process     # no server needed: talks to the MCPServer object in memory
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import Client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")


def target():
    if "--in-process" in sys.argv or os.getenv("MCP_IN_PROCESS") == "1":
        from mcp_server import mcp
        return mcp
    return MCP_URL


def tool_payload(result) -> object:
    """Prefer structured content; fall back to the first text block."""
    if getattr(result, "structured_content", None):
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    for block in result.content:
        if getattr(block, "text", None):
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return block.text
    return None


async def main():
    async with Client(target()) as client:
        tools = await client.list_tools()
        print("TOOLS:", [t.name for t in tools.tools])
        r = await client.call_tool("search_faq", {"query": "driving licence renewal fee", "service": "driving"})
        print("search_faq ->", json.dumps(tool_payload(r), indent=2)[:600])
        r = await client.call_tool("submit_application",
                                   {"service": "driving", "applicant_ref": "LAB-001",
                                    "details": "licence renewal", "dry_run": True})
        print("submit_application(dry_run) ->", tool_payload(r))


if __name__ == "__main__":
    asyncio.run(main())
