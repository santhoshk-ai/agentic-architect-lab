"""Prompt/model versioning with an eval gate, the LLMOps loop in miniature.

Runs each prompt version over cases.json on one model, logs every call (prompt_version tagged) to ../usage.jsonl,
and writes eval_results.json: accuracy, tokens, cost/case, p50/p95 latency, failures.
  python prompt_ab.py triage_v1 triage_v2
  MODEL=<other model id> python prompt_ab.py triage_v2      # same prompt, different model = model A/B
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

import boto3
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.usage import log_call  # noqa: E402

load_dotenv(HERE.parent / ".env")
MODEL = os.getenv("MODEL", os.getenv("NOVA_LITE_PROFILE", "us.amazon.nova-2-lite-v1:0"))
brt = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))


def parse_intent(text: str) -> str:
    s = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(s).get("intent", "PARSE_ERROR")
    except (json.JSONDecodeError, AttributeError):
        return "PARSE_ERROR"


def run_version(version: str, cases: list) -> dict:
    system = (HERE / "prompts" / f"{version}.txt").read_text()
    lat, tin, tout, cost, fails = [], 0, 0, 0.0, []
    for c in cases:
        t0 = time.time()
        r = brt.converse(modelId=MODEL, system=[{"text": system}],
                         messages=[{"role": "user", "content": [{"text": f"<message>{c['text']}</message>"}]}],
                         inferenceConfig={"maxTokens": 50, "temperature": 0})
        ms = int((time.time() - t0) * 1000)
        got = parse_intent(r["output"]["message"]["content"][0]["text"])
        rec = log_call(source="E_prompt_ab", model=MODEL, prompt_version=version, input_tokens=r["usage"]["inputTokens"],
                       output_tokens=r["usage"]["outputTokens"], latency_ms=ms,
                       extra={"expected": c["intent"], "got": got})
        lat.append(ms); tin += rec["input_tokens"]; tout += rec["output_tokens"]; cost += rec["cost_usd"]
        if got != c["intent"]:
            fails.append({"text": c["text"][:70], "expected": c["intent"], "got": got})
    lat.sort()
    return {"prompt_version": version, "model": MODEL, "n": len(cases),
            "accuracy": round(1 - len(fails) / len(cases), 3), "input_tokens": tin, "output_tokens": tout,
            "cost_per_case_usd": round(cost / len(cases), 7), "p50_ms": lat[len(lat) // 2],
            "p95_ms": lat[min(len(lat) - 1, int(0.95 * len(lat)))], "mean_ms": int(statistics.mean(lat)),
            "failures": fails}


if __name__ == "__main__":
    versions = sys.argv[1:] or ["triage_v1", "triage_v2"]
    cases = json.loads((HERE / "cases.json").read_text())
    out_path = HERE / "eval_results.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    for v in versions:
        res = run_version(v, cases)
        results[f"{v}@{MODEL}"] = res
        print(f"{v:10} acc={res['accuracy']:.2f} in={res['input_tokens']} out={res['output_tokens']} "
              f"p50={res['p50_ms']}ms p95={res['p95_ms']}ms cost/case=${res['cost_per_case_usd']}")
        for f in res["failures"]:
            print(f"   MISS expected={f['expected']:9} got={f['got']:11} | {f['text']}")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out_path.name}. Next: python promote_gate.py triage_v2")
