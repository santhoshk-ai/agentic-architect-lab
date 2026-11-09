# Local:  MCP_URL=http://localhost:8000/mcp python client_check.py
# Remote: MCP_URL=<runtime or gateway url> BEARER_TOKEN=... python client_check.py
import asyncio, os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    url = os.environ["MCP_URL"]
    tok = os.getenv("BEARER_TOKEN")
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    async with streamablehttp_client(url, headers, timeout=120, terminate_on_close=False) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            names = [t.name for t in tools]
            print("TOOLS:", names)
            fee = next(n for n in names if n.endswith("get_service_fee"))
            res = await s.call_tool(fee, {"service": "residency_renewal"})
            print("CALL:", fee, "->", "".join(getattr(c, "text", "") for c in res.content))

asyncio.run(main())
