"""Wednesday's row: re-index the same corpus with fixed, semantic and hierarchical chunking
and ask the same 10 questions. Chunking is fixed per data source, so each strategy gets its
own KB + S3 Vectors index (no stale vectors, all three stay live for side-by-side checks).

Usage: python chunking_compare.py [--k 3] [--strategies fixed semantic hierarchical]
Writes chunking_results.json and prints the markdown table for results.md.
"""
import argparse
import json
import time
from pathlib import PurePosixPath

import config as C
import kb_lib as L


def norm(s):
    return " ".join(s.split()).lower()


def src(r):
    return PurePosixPath(r.get("location", {}).get("s3Location", {}).get("uri", "")).name


def evaluate(rt, kb_id, questions, k):
    rows, words, returned, hits, right_doc, ms = [], [], 0, 0, 0, []
    for q in questions:
        t0 = time.time()
        res = rt.retrieve(knowledgeBaseId=kb_id, retrievalQuery={"text": q["q"]},
                          retrievalConfiguration={"vectorSearchConfiguration":
                                                  {"numberOfResults": k}})["retrievalResults"]
        ms.append((time.time() - t0) * 1000)
        texts = [norm(r["content"]["text"]) for r in res]
        rank = next((i + 1 for i, t in enumerate(texts) if norm(q["expect"]) in t), None)
        doc_rank = next((i + 1 for i, r in enumerate(res) if src(r) == q["doc"]), None)
        hits += rank is not None
        right_doc += doc_rank is not None
        returned += len(res)
        words += [len(t.split()) for t in texts]
        rows.append({"q": q["q"], "phrase_rank": rank, "doc_rank": doc_rank,
                     "sources": [src(r) for r in res],
                     "scores": [round(r.get("score", 0), 3) for r in res]})
    n = len(questions)
    return rows, {
        f"hit@{k}": f"{hits}/{n}",              # answer phrase inside a returned chunk
        f"doc@{k}": f"{right_doc}/{n}",         # right document, phrase may be cut off
        "avg_chunk_words": round(sum(words) / max(len(words), 1)),
        "results_returned": f"{returned}/{n * k}",
        "avg_retrieve_ms": round(sum(ms) / n),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--strategies", nargs="+", default=list(C.STRATEGIES), choices=list(C.STRATEGIES))
    a = ap.parse_args()

    cl = L.clients()
    state = L.load_state()
    L.provision_base(state, cl)
    questions = json.loads((C.HERE / "questions.json").read_text())

    summary, all_rows = [], []
    for s in a.strategies:
        print(f"\n== {s}")
        rec = L.ensure_kb(state, cl, s)
        rows, stats = evaluate(cl["rt"], rec["kb_id"], questions, a.k)
        for r in rows:
            mark = f"phrase@{r['phrase_rank']}" if r["phrase_rank"] else (
                f"doc@{r['doc_rank']} phrase MISSING" if r["doc_rank"] else "MISS")
            print(f"  {mark:<24} {r['q'][:70]}")
        summary.append({"strategy": s, **stats, "ingest_seconds": rec.get("ingest_seconds")})
        all_rows += [{"strategy": s, **r} for r in rows]

    (C.HERE / "chunking_results.json").write_text(
        json.dumps({"k": a.k, "summary": summary, "rows": all_rows}, indent=2))

    k = a.k
    print(f"\n| Strategy | hit@{k} | doc@{k} | Avg chunk words | Results returned | Avg retrieve ms | Ingest s |")
    print("|---|---|---|---|---|---|---|")
    for r in summary:
        print(f"| {r['strategy']} | {r[f'hit@{k}']} | {r[f'doc@{k}']} | {r['avg_chunk_words']} | "
              f"{r['results_returned']} | {r['avg_retrieve_ms']} | {r['ingest_seconds']} |")

    # per-question matrix: where strategies disagree is where the lesson is
    print(f"\n| Question | " + " | ".join(a.strategies) + " |")
    print("|---|" + "---|" * len(a.strategies))
    for i, q in enumerate(questions):
        cells = []
        for s in a.strategies:
            r = next(x for x in all_rows if x["strategy"] == s and x["q"] == q["q"])
            cells.append(str(r["phrase_rank"] or "-"))
        print(f"| {q['q'][:60]} | " + " | ".join(cells) + " |")
    print("\nWrote chunking_results.json")


if __name__ == "__main__":
    main()
