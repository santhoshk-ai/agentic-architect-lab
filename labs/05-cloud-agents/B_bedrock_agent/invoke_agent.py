"""Invokes the Bedrock Agent with enableTrace=True and prints what the managed loop actually did.

Usage:
  python invoke_agent.py "How much is a residency renewal and what's the status of APP-1002?"
  python invoke_agent.py "Submit a residency renewal for Aisha Rahman" --decide ask|confirm|deny
  python invoke_agent.py "..." --alias TSTALIASID      # DRAFT (test alias) instead of v1

What to look for in the trace: rationale (the model's plan), invocationInput (tool + params chosen),
observation (tool result / final answer), and per-step token usage -> logged to ../usage.jsonl.
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.usage import log_call  # noqa: E402

state = json.loads((HERE / "agent_state.json").read_text())
rt = boto3.client("bedrock-agent-runtime", region_name=state["region"])


def show_trace(t: dict, alias: str):
    ot = t.get("orchestrationTrace") or {}
    if "rationale" in ot:
        print("  [plan]   ", ot["rationale"].get("text", "")[:300])
    inv = (ot.get("invocationInput") or {}).get("actionGroupInvocationInput")
    if inv:
        print("  [tool]   ", inv.get("function"), {p["name"]: p["value"] for p in inv.get("parameters", [])})
    obs = ot.get("observation") or {}
    if "actionGroupInvocationOutput" in obs:
        print("  [result] ", obs["actionGroupInvocationOutput"].get("text", "")[:200])
    if "finalResponse" in obs:
        print("  [final]  ", obs["finalResponse"].get("text", "")[:200])
    meta = (ot.get("modelInvocationOutput") or {}).get("metadata") or {}
    if "usage" in meta:
        u = meta["usage"]
        log_call(source="B_bedrock_agent", model=state["model"], prompt_version=f"alias:{alias}",
                 input_tokens=u.get("inputTokens", 0), output_tokens=u.get("outputTokens", 0),
                 latency_ms=meta.get("totalTimeMs", 0))
        print(f"  [usage]   in={u.get('inputTokens')} out={u.get('outputTokens')} ms={meta.get('totalTimeMs')}")
    if t.get("failureTrace"):
        print("  [FAIL]   ", t["failureTrace"].get("failureReason"))
    if t.get("guardrailTrace"):
        print("  [guard]  ", t["guardrailTrace"].get("action"))


def invoke(text: str | None, session: str, alias: str, decide: str, session_state: dict | None = None):
    kw = {"agentId": state["agentId"], "agentAliasId": alias, "sessionId": session, "enableTrace": True}
    if text:
        kw["inputText"] = text
    if session_state:
        kw["sessionState"] = session_state
    t0 = time.time()
    answer = ""
    for ev in rt.invoke_agent(**kw)["completion"]:
        if "trace" in ev:
            show_trace(ev["trace"]["trace"], alias)
        elif "chunk" in ev:
            answer += ev["chunk"]["bytes"].decode()
        elif "returnControl" in ev:
            rc = ev["returnControl"]
            results = []
            for ii in rc["invocationInputs"]:
                fi = ii["functionInvocationInput"]
                params = {p["name"]: p["value"] for p in fi.get("parameters", [])}
                print(f"\n  >>> HUMAN APPROVAL NEEDED ({fi.get('actionInvocationType')}): {fi['function']} {params}")
                ok = decide == "confirm" or (decide == "ask" and input("  approve? [y/N] ").strip().lower() == "y")
                results.append({"functionResult": {"actionGroup": fi["actionGroup"], "function": fi["function"],
                                                   "confirmationState": "CONFIRM" if ok else "DENY"}})
                print("  >>>", "CONFIRMED" if ok else "DENIED")
            return invoke(None, session, alias, decide,
                          {"invocationId": rc["invocationId"], "returnControlInvocationResults": results})
    print(f"\nANSWER ({int((time.time() - t0) * 1000)} ms): {answer}")
    return answer


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default="How much is a residency renewal, and what is the status of APP-1002?")
    ap.add_argument("--alias", default=state["aliasId"])
    ap.add_argument("--session", default=str(uuid.uuid4()))
    ap.add_argument("--decide", choices=["ask", "confirm", "deny"], default="ask")
    a = ap.parse_args()
    print(f"agent={state['agentId']} alias={a.alias} session={a.session}")
    invoke(a.question, a.session, a.alias, a.decide)
