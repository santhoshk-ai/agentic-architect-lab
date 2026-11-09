"""Raw Bedrock Converse tool loop over MCP tools discovered through AgentCore Gateway.

Learning points: the agent knows ONE endpoint (the Gateway) and ONE credential (its JWT). Tool discovery,
routing to Lambda / MCP targets and outbound credentials are the Gateway's job. Every model call is logged
to ../usage.jsonl (tokens, latency, cost, prompt_version) and MAX_TURNS caps runaway loops.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import boto3
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.usage import log_call  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
MODEL = os.getenv("NOVA_LITE_PROFILE", "us.amazon.nova-2-lite-v1:0")
REGION = os.getenv("AWS_REGION", "us-east-1")
PROMPT_VERSION = "gw-agent-v1"
MAX_TURNS = 5
SYSTEM = [{"text": "You are a Nova City services assistant. Use a tool for every fee or status; never guess. "
                   "If a tool returns an error, say you could not find it. Answer in at most 2 sentences."}]


def clean_schema(schema: dict) -> dict:
    """Drop JSON-schema keys some models reject in toolSpec."""
    return {k: v for k, v in schema.items() if k not in ("$schema", "title")}


async def run(question: str) -> str:
    url, token = os.environ["GATEWAY_URL"], os.environ["BEARER_TOKEN"]
    brt = boto3.client("bedrock-runtime", region_name=REGION)
    async with streamablehttp_client(url, {"Authorization": f"Bearer {token}"}, timeout=120) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            print("tools:", [t.name for t in tools])
            spec = [{"toolSpec": {"name": t.name, "description": t.description or t.name,
                                  "inputSchema": {"json": clean_schema(t.inputSchema)}}} for t in tools]
            msgs = [{"role": "user", "content": [{"text": question}]}]
            for turn in range(1, MAX_TURNS + 1):
                t0 = time.time()
                resp = brt.converse(modelId=MODEL, system=SYSTEM, messages=msgs,
                                    toolConfig={"tools": spec}, inferenceConfig={"maxTokens": 400})
                out = resp["output"]["message"]
                msgs.append(out)
                calls = [c["toolUse"] for c in out["content"] if "toolUse" in c]
                log_call(source="A_gateway_agent", model=MODEL, prompt_version=PROMPT_VERSION,
                         input_tokens=resp["usage"]["inputTokens"], output_tokens=resp["usage"]["outputTokens"],
                         latency_ms=int((time.time() - t0) * 1000), tools=[c["name"] for c in calls],
                         extra={"turn": turn, "stop": resp["stopReason"]})
                if resp["stopReason"] != "tool_use":
                    answer = "".join(c.get("text", "") for c in out["content"])
                    print(f"ANSWER (turn {turn}):", answer)
                    return answer
                results = []
                for c in calls:
                    res = await s.call_tool(c["name"], c["input"])
                    txt = "".join(getattr(x, "text", "") for x in res.content)
                    print(f"  turn {turn}: {c['name']}({c['input']}) -> {txt[:120]}")
                    results.append({"toolResult": {"toolUseId": c["toolUseId"], "content": [{"text": txt}],
                                                   "status": "error" if res.isError else "success"}})
                msgs.append({"role": "user", "content": results})
            print("STOPPED: MAX_TURNS reached (runaway guard)")
            return ""


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "How much is a residency renewal, and what is the status of APP-1002?"
    asyncio.run(run(q))
