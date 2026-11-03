"""
Block 2 - evaluation.

    hit@3 before re-rank  (vector top-3)
    hit@3 after  re-rank  (vector top-8 -> re-rank -> top-3)
    grounding pass rate   (answers judged grounded by the guardrail)
    ungrounded probe      (a fabricated answer MUST be blocked)

Done when: hit@3 after re-rank >= 8/10 AND the ungrounded probe is blocked.
Writes eval_results.json - paste the summary into results.md.
"""
from __future__ import annotations

import json
import time

from data import EVAL, FAQS, UNGROUNDED_CASE
from rag import (EMBED_MODEL, EMBED_PROVIDER, RERANK, VECTOR_STORE, answer, check_grounding,
                 context_block, rerank, search)


def main(with_answers: bool = True) -> dict:
    rows, before, after, grounded = [], 0, 0, 0
    for case in EVAL:
        t0 = time.perf_counter()
        hits8 = search(case["q"], k=8)
        top3_vec = [h["id"] for h in hits8[:3]]
        top3 = rerank(case["q"], hits8, 3)
        top3_rr = [h["id"] for h in top3]
        b, a = case["expected"] in top3_vec, case["expected"] in top3_rr
        before += b
        after += a
        row = {"q": case["q"], "expected": case["expected"], "vector_top3": top3_vec,
               "rerank_top3": top3_rr, "hit_before": b, "hit_after": a}
        if with_answers:
            ans = answer(case["q"], top3)
            g = check_grounding(case["q"], context_block(top3), ans["answer"])
            grounded += g["grounded"]
            row.update(answer=ans["answer"], grounding=g)
        row["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        rows.append(row)
        print(f"{'OK ' if a else 'MISS'} {case['expected']} vec={top3_vec} rr={top3_rr}  {case['q']}")

    ctx = next(f for f in FAQS if f["id"] == UNGROUNDED_CASE["context_id"])
    probe = check_grounding(UNGROUNDED_CASE["q"], f"[{ctx['id']}] {ctx['body']}", UNGROUNDED_CASE["bad_answer"])
    n = len(EVAL)
    summary = {
        "config": f"embed={EMBED_PROVIDER}:{EMBED_MODEL} store={VECTOR_STORE} rerank={RERANK}",
        "hit@3_before_rerank": f"{before}/{n}",
        "hit@3_after_rerank": f"{after}/{n}",
        "grounding_pass_rate": f"{grounded}/{n}" if with_answers else "skipped",
        "ungrounded_probe_blocked": not probe["grounded"],
        "ungrounded_probe": probe,
        "done_when": after >= 8 and not probe["grounded"] and EMBED_PROVIDER != "mock",
    }
    if EMBED_PROVIDER == "mock":
        summary["note"] = "mock embeddings are lexical-only: run with real embeddings to claim the Done-when"
    json.dump({"summary": summary, "rows": rows}, open("eval_results.json", "w"), indent=2)
    print("\n" + json.dumps(summary, indent=2))
    print("\nDONE-WHEN:", "PASS" if summary["done_when"] else "NOT YET")
    return summary


if __name__ == "__main__":
    import sys
    main(with_answers="--no-answers" not in sys.argv)
