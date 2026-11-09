"""Eval gate for promoting a prompt/model version to production in model_registry.json.

Rule (edit to taste, but write it down. In government, the rule IS the governance):
  candidate.accuracy >= production.accuracy  AND  cost_per_case <= COST_TOLERANCE x production  AND  no PARSE_ERROR
  python promote_gate.py triage_v2 [--model <id>] [--approver "Santhosh"] [--dry-run]
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
COST_TOLERANCE = 1.5


def decide(cand: dict, prod: dict | None) -> tuple[bool, list[str]]:
    reasons = []
    if any(f["got"] == "PARSE_ERROR" for f in cand["failures"]):
        reasons.append("candidate produced unparseable output")
    if prod:
        if cand["accuracy"] < prod["accuracy"]:
            reasons.append(f"accuracy {cand['accuracy']} < production {prod['accuracy']}")
        if prod["cost_per_case_usd"] and cand["cost_per_case_usd"] > COST_TOLERANCE * prod["cost_per_case_usd"]:
            reasons.append(f"cost/case {cand['cost_per_case_usd']} > {COST_TOLERANCE}x production")
    return (not reasons), reasons


def main(a):
    reg_path, res_path = HERE / "model_registry.json", HERE / "eval_results.json"
    reg, results = json.loads(reg_path.read_text()), json.loads(res_path.read_text())
    model = a.model or os.getenv("NOVA_LITE_PROFILE", "us.amazon.nova-2-lite-v1:0")
    cand = results[f"{a.version}@{model}"]
    cur = reg["triage"]["production"]
    prod = results.get(f"{cur['prompt_version']}@{cur['model']}")
    ok, reasons = decide(cand, prod)
    print(f"candidate {a.version}@{model}: acc={cand['accuracy']} cost/case={cand['cost_per_case_usd']}")
    print(f"production {cur['prompt_version']}@{cur['model']}: " +
          (f"acc={prod['accuracy']} cost/case={prod['cost_per_case_usd']}" if prod else "no eval on file"))
    print("DECISION:", "PROMOTE" if ok else "REJECT", "|", "; ".join(reasons) or "all gates passed")
    if ok and not a.dry_run:
        reg["triage"]["history"].append(cur)
        reg["triage"]["production"] = {"prompt_version": a.version, "model": model, "accuracy": cand["accuracy"],
                                       "cost_per_case_usd": cand["cost_per_case_usd"],
                                       "promoted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                       "approved_by": a.approver}
        reg_path.write_text(json.dumps(reg, indent=2))
        print("model_registry.json updated (commit it: the git log is your audit trail)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--model")
    ap.add_argument("--approver", default="lab-owner")
    ap.add_argument("--dry-run", action="store_true")
    main(ap.parse_args())
