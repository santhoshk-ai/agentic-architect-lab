"""
Block 1 - tool calling with a raw agent loop (no framework).

The loop:  model -> (tool call?) -> run tool in OUR code -> feed result back -> repeat
Guard rails that live OUTSIDE the model: MAX_TURNS and an allow-list of tools.

Memory: the model is stateless, so pass the same `history` list to every run() call.
Each loop appends to it in place (in its provider's message format, tool calls included).
"""
from __future__ import annotations

import os
import sys

from llm import AWS_REGION, BEDROCK_MODEL, GEMINI_MODEL, PROVIDER, bedrock_client, gemini_client

MAX_TURNS = int(os.getenv("MAX_TURNS", "5"))

# ---------------------------------------------------------------- the tools (plain Python)
APPOINTMENTS = {
    "residency": ["2026-11-04 09:30", "2026-11-05 11:00"],
    "driving": ["2026-11-03 14:00", "2026-11-06 10:15"],
}
FEES_AED = {"residency": 350, "driving": 120, "general": 0}


def get_appointment_slots(service: str) -> dict:
    return {"service": service, "slots": APPOINTMENTS.get(service, [])}


def get_fee(service: str) -> dict:
    return {"service": service, "fee_aed": FEES_AED.get(service)}


TOOLS = {"get_appointment_slots": get_appointment_slots, "get_fee": get_fee}

SCHEMA = {
    "type": "object",
    "properties": {"service": {"type": "string", "enum": ["residency", "driving", "general"]}},
    "required": ["service"],
}
SPECS = [
    ("get_appointment_slots", "List the next free appointment slots for a Nova City service."),
    ("get_fee", "Return the service fee in AED for a Nova City service."),
]
SYSTEM = "You are a Nova City Services assistant. Use tools for slots and fees; never guess them. Be brief. DO not repeat the driving slot without checking the tool every time, but fee wont cange so you can persist for 10 mins."


def run_tool(name: str, args: dict) -> dict:
    if name not in TOOLS:                       # allow-list
        return {"error": f"tool {name} not allowed"}
    return TOOLS[name](**args)


# ---------------------------------------------------------------- Bedrock Converse loop
def run_bedrock(question: str, history: list | None = None) -> str:
    tool_config = {"tools": [{"toolSpec": {"name": n, "description": d, "inputSchema": {"json": SCHEMA}}}
                             for n, d in SPECS]}
    messages = history if history is not None else []
    messages.append({"role": "user", "content": [{"text": question}]})
    for turn in range(1, MAX_TURNS + 1):
        r = bedrock_client().converse(modelId=BEDROCK_MODEL, system=[{"text": SYSTEM}],
                                      messages=messages, toolConfig=tool_config,
                                      inferenceConfig={"maxTokens": 400})
        msg = r["output"]["message"]
        messages.append(msg)
        print(f"  turn {turn}: stopReason={r['stopReason']} tokens={r['usage']['totalTokens']}")
        if r["stopReason"] != "tool_use":
            return "".join(b.get("text", "") for b in msg["content"])
        results = []
        for b in msg["content"]:
            if "toolUse" in b:
                tu = b["toolUse"]
                out = run_tool(tu["name"], tu["input"])
                print(f"    tool {tu['name']}({tu['input']}) -> {out}")
                results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"json": out}]}})
        messages.append({"role": "user", "content": results})
    stop = f"Stopped: MAX_TURNS={MAX_TURNS} reached"
    messages.append({"role": "assistant", "content": [{"text": stop}]})  # keep user/assistant alternation
    return stop


# ---------------------------------------------------------------- Gemini loop (manual function calling)
def run_gemini(question: str, history: list | None = None) -> str:
    from google.genai import types
    decls = [types.FunctionDeclaration(name=n, description=d, parameters_json_schema=SCHEMA) for n, d in SPECS]
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM, tools=[types.Tool(function_declarations=decls)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    contents = history if history is not None else []
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    for turn in range(1, MAX_TURNS + 1):
        r = gemini_client().models.generate_content(model=GEMINI_MODEL, contents=contents, config=cfg)
        calls = r.function_calls or []
        print(f"  turn {turn}: function_calls={len(calls)}")
        if not calls:
            contents.append(r.candidates[0].content)
            return r.text or ""
        contents.append(r.candidates[0].content)
        parts = []
        for c in calls:
            out = run_tool(c.name, dict(c.args or {}))
            print(f"    tool {c.name}({dict(c.args or {})}) -> {out}")
            parts.append(types.Part.from_function_response(name=c.name, response=out))
        contents.append(types.Content(role="user", parts=parts))
    stop = f"Stopped: MAX_TURNS={MAX_TURNS} reached"
    contents.append(types.Content(role="model", parts=[types.Part(text=stop)]))
    return stop


# ---------------------------------------------------------------- offline mock loop
def run_mock(question: str, history: list | None = None) -> str:
    from llm import mock_service
    service = mock_service(question) or "general"
    slots = run_tool("get_appointment_slots", {"service": service})
    fee = run_tool("get_fee", {"service": service})
    print(f"  turn 1: tool_use x2 -> {slots}, {fee}")
    print("  turn 2: end_turn")
    answer = f"Next {service} slots: {', '.join(slots['slots']) or 'none'}; fee AED {fee['fee_aed']}."
    if history is not None:
        history += [{"role": "user", "text": question}, {"role": "assistant", "text": answer}]
    return answer


def run(question: str, provider: str | None = None, history: list | None = None) -> str:
    """history: one list per conversation (and per provider); reuse it across calls."""
    p = (provider or PROVIDER).lower()
    return {"bedrock": run_bedrock, "gemini": run_gemini, "mock": run_mock}[p](question, history)


if __name__ == "__main__":
    print(f"provider={PROVIDER} region={AWS_REGION} max_turns={MAX_TURNS}")
    if sys.argv[1:]:                                # one-shot: python tools_loop.py "question"
        print("\nANSWER:", run(" ".join(sys.argv[1:])))
    else:                                           # chat: same history every turn
        history: list = []
        print("Chat mode - empty line or 'exit' to quit.")
        while (q := input("\nyou> ").strip()) and q.lower() not in ("exit", "quit"):
            print("\nANSWER:", run(q, history=history))
            print(f"  (history: {len(history)} messages)")
