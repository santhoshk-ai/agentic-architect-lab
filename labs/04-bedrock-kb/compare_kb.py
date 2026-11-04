"""Tuesday's row: Retrieve vs RetrieveAndGenerate on the same KB, with citations,
an out-of-corpus trap, and a metadata-filter demo (Wednesday's row).

Usage: python compare_kb.py [--strategy fixed] [--k 5]
Writes kb_compare.json and prints markdown tables for results.md.
"""
import argparse
import json
import time
from pathlib import PurePosixPath

import config as C
import kb_lib as L


def src(location):
    uri = (location or {}).get("s3Location", {}).get("uri", "")
    return PurePosixPath(uri).name or "?"


def norm(s):
    return " ".join(s.split()).lower()


def retrieve(rt, kb_id, q, k, flt=None):
    vs = {"numberOfResults": k}
    if flt:
        vs["filter"] = flt
    t0 = time.time()
    res = rt.retrieve(knowledgeBaseId=kb_id, retrievalQuery={"text": q},
                      retrievalConfiguration={"vectorSearchConfiguration": vs})["retrievalResults"]
    return res, round((time.time() - t0) * 1000)


def rag(rt, kb_id, q, k, model_arn):
    t0 = time.time()
    out = rt.retrieve_and_generate(
        input={"text": q},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": kb_id,
                "modelArn": model_arn,
                "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": k}},
            },
        },
    )
    ms = round((time.time() - t0) * 1000)
    cites = []
    for c in out.get("citations", []):
        span = c.get("generatedResponsePart", {}).get("textResponsePart", {}).get("text", "")
        for ref in c.get("retrievedReferences", []):
            cites.append({"source": src(ref.get("location")), "claim": span[:90]})
    return out["output"]["text"], cites, ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="fixed", choices=list(C.STRATEGIES))
    ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args()

    state = L.load_state()
    if a.strategy not in state.get("kbs", {}):
        raise SystemExit(f"No KB for '{a.strategy}'. Run: python setup_kb.py --strategy {a.strategy}")
    kb_id = state["kbs"][a.strategy]["kb_id"]
    cl = L.clients()
    rt = cl["rt"]
    model_arn = L.gen_model_arn(state["account"])
    questions = json.loads((C.HERE / "compare_questions.json").read_text())

    rows = []
    for q in questions:
        res, r_ms = retrieve(rt, kb_id, q["q"], a.k)
        top = [{"source": src(r.get("location")), "score": round(r.get("score", 0), 3)} for r in res[:3]]
        hit = None
        if q.get("expect"):
            hit = any(norm(q["expect"]) in norm(r["content"]["text"]) for r in res[:3])
        answer, cites, g_ms = rag(rt, kb_id, q["q"], a.k, model_arn)
        rows.append({"q": q["q"], "out_of_corpus": bool(q.get("out_of_corpus")),
                     "retrieve_top3": top, "retrieve_hit@3": hit, "retrieve_ms": r_ms,
                     "answer": answer, "citations": cites, "rag_ms": g_ms})
        print(f"\nQ: {q['q']}")
        print(f"  Retrieve ({r_ms} ms): " + ", ".join(f"{t['source']}@{t['score']}" for t in top)
              + ("" if hit is None else f"  hit@3={hit}"))
        print(f"  RetrieveAndGenerate ({g_ms} ms): {answer[:220]}")
        print(f"  citations: {sorted({c['source'] for c in cites}) or 'NONE'}")

    # metadata filter demo: an ambiguous question, with and without service=driving
    amb = "How early can I renew?"
    plain, _ = retrieve(rt, kb_id, amb, 3)
    filt, _ = retrieve(rt, kb_id, amb, 3, {"equals": {"key": "service", "value": "driving"}})
    demo = {"q": amb,
            "no_filter": [src(r.get("location")) for r in plain],
            "service=driving": [src(r.get("location")) for r in filt]}

    out = {"strategy": a.strategy, "k": a.k, "gen_model": C.GEN_MODEL_ID,
           "rows": rows, "filter_demo": demo}
    (C.HERE / "kb_compare.json").write_text(json.dumps(out, indent=2))

    print("\n| Question | Retrieve top-3 sources | hit@3 | RAG cites | Retrieve ms | RAG ms |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        s = ", ".join(t["source"] for t in r["retrieve_top3"])
        c = ", ".join(sorted({x["source"] for x in r["citations"]})) or "none"
        h = "trap" if r["out_of_corpus"] else r["retrieve_hit@3"]
        print(f"| {r['q']} | {s} | {h} | {c} | {r['retrieve_ms']} | {r['rag_ms']} |")
    print(f"\nFilter demo '{amb}':\n  no filter      -> {demo['no_filter']}"
          f"\n  service=driving -> {demo['service=driving']}")
    print("\nWrote kb_compare.json")


if __name__ == "__main__":
    main()
