"""Shared LLMOps logger: one JSON line per model call, appended to usage.jsonl at the lab root.

Every block (A gateway agent, B Bedrock Agent, C three providers, E prompt A/B) writes the same schema,
so one report compares providers, prompt versions and agents side by side.
"""
import collections
import json
import os
import time
from pathlib import Path

LOG = Path(os.getenv("USAGE_LOG", Path(__file__).resolve().parent.parent / "usage.jsonl"))


def price(model: str) -> tuple[float, float]:
    """USD per 1M (input, output) tokens from env PRICE_<KEY>_IN / _OUT. Fill from the provider pricing pages.
    KEY = model id upper-cased with non-alphanumerics -> '_', e.g. US_AMAZON_NOVA_2_LITE_V1_0."""
    key = "".join(c if c.isalnum() else "_" for c in model).upper()
    return float(os.getenv(f"PRICE_{key}_IN", "0")), float(os.getenv(f"PRICE_{key}_OUT", "0"))


def log_call(*, source: str, model: str, input_tokens: int, output_tokens: int, latency_ms: int,
             prompt_version: str = "-", tools=None, extra: dict | None = None) -> dict:
    p_in, p_out = price(model)
    rec = {"ts": round(time.time(), 3), "source": source, "model": model, "prompt_version": prompt_version,
           "input_tokens": int(input_tokens or 0), "output_tokens": int(output_tokens or 0),
           "latency_ms": int(latency_ms), "cost_usd": round(((input_tokens or 0) * p_in + (output_tokens or 0) * p_out) / 1e6, 6),
           "tools": list(tools or [])}
    if extra:
        rec.update(extra)
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def report(path: Path = LOG) -> list[str]:
    agg = collections.defaultdict(collections.Counter)
    lat = collections.defaultdict(list)
    for line in open(path):
        r = json.loads(line)
        k = (r["source"], r["model"], r["prompt_version"])
        a = agg[k]
        a["calls"] += 1
        a["in"] += r["input_tokens"]
        a["out"] += r["output_tokens"]
        a["usd_micro"] += int(r["cost_usd"] * 1e6)
        lat[k].append(r["latency_ms"])
    rows = ["source | model | prompt_version | calls | in_tok | out_tok | p50_ms | cost_usd"]
    for k, a in sorted(agg.items()):
        p50 = sorted(lat[k])[len(lat[k]) // 2]
        rows.append(f"{k[0]} | {k[1]} | {k[2]} | {a['calls']} | {a['in']} | {a['out']} | {p50} | {a['usd_micro'] / 1e6:.6f}")
    return rows


if __name__ == "__main__":
    print("\n".join(report()))
