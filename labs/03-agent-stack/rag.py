"""
Block 2 - RAG end to end.

    ingest:   FAQ -> embedding (Gemini Embedding 2, 768d) -> vector store (memory | pgvector)
    retrieve: query embedding -> top-k=8 by cosine (+ optional metadata filter on service)
              -> re-rank (Cohere Rerank 3.5 on Bedrock | lexical fallback) -> top-3
    answer:   cited answer from the top-3 only
    check:    contextual grounding guardrail (Bedrock ApplyGuardrail | local overlap fallback)

CLI:
    python rag.py ingest
    python rag.py ask "How much does a driving licence renewal cost?"
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import zlib
from pathlib import Path

import numpy as np

from data import FAQS
from llm import AWS_REGION, PROVIDER, ask, gemini_client

EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "gemini" if PROVIDER != "mock" else "mock").lower()
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-2")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
VECTOR_STORE = os.getenv("VECTOR_STORE", "memory").lower()
PG_DSN = os.getenv("PG_DSN", "postgresql://lab:lab@localhost:5432/lab")
RERANK = os.getenv("RERANK", "bedrock" if PROVIDER != "mock" else "lexical").lower()
RERANK_MODEL_ARN = os.getenv("RERANK_MODEL_ARN") or \
    f"arn:aws:bedrock:{AWS_REGION}::foundation-model/cohere.rerank-v3-5:0"
GUARDRAIL_ID = os.getenv("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.getenv("GUARDRAIL_VERSION", "DRAFT")
INDEX_FILE = Path(__file__).with_name(".index.json")

# Gemini Embedding 2 takes the task as a text prefix (task_type is not supported for this model).
QUERY_PREFIX = "task: question answering | query: {text}"
DOC_PREFIX = "title: {title} | text: {text}"


# ================================================================= embeddings
def embed(texts: list[str], kind: str = "query", titles: list[str] | None = None) -> np.ndarray:
    if EMBED_PROVIDER == "gemini":
        from google.genai import types
        cfg = types.EmbedContentConfig(output_dimensionality=EMBED_DIM)
        vecs = []
        for i, t in enumerate(texts):  # one call per text: a list in one call is aggregated into ONE vector
            text = QUERY_PREFIX.format(text=t) if kind == "query" else \
                DOC_PREFIX.format(title=(titles[i] if titles else "none"), text=t)
            r = gemini_client().models.embed_content(model=EMBED_MODEL, contents=text, config=cfg)
            vecs.append(r.embeddings[0].values)
        arr = np.array(vecs, dtype=np.float32)
    elif EMBED_PROVIDER == "mock":
        arr = np.stack([_hash_embed(t) for t in texts])
    else:
        raise ValueError(f"Unknown EMBED_PROVIDER {EMBED_PROVIDER}")
    return arr / np.linalg.norm(arr, axis=1, keepdims=True)  # cosine = dot product


_STOP = set("a an the of to for and or is are can i my do does what how when where with in on at be it you".split())


def _tokens(text: str) -> list[str]:
    return [w.rstrip("s") for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP]


def _hash_embed(text: str) -> np.ndarray:
    """Offline stand-in: hashed bag of words + bigrams. Lexical only - no semantics."""
    v = np.zeros(EMBED_DIM, dtype=np.float32)
    toks = _tokens(text)
    for tok in toks + [a + "_" + b for a, b in zip(toks, toks[1:])]:
        v[zlib.crc32(tok.encode()) % EMBED_DIM] += 1.0
    return v if v.any() else v + 1e-6


# ================================================================= vector stores
class MemoryStore:
    """Numpy cosine search, persisted to .index.json so other processes (MCP server) can load it."""

    def __init__(self):
        self.rows: list[dict] = []
        self.matrix = np.zeros((0, EMBED_DIM), dtype=np.float32)
        if INDEX_FILE.exists():
            saved = json.loads(INDEX_FILE.read_text())
            if saved.get("embed") == f"{EMBED_PROVIDER}:{EMBED_MODEL}:{EMBED_DIM}":
                self.rows = saved["rows"]
                self.matrix = np.array(saved["vectors"], dtype=np.float32)

    def upsert(self, rows: list[dict], vectors: np.ndarray):
        self.rows, self.matrix = rows, vectors
        INDEX_FILE.write_text(json.dumps({"embed": f"{EMBED_PROVIDER}:{EMBED_MODEL}:{EMBED_DIM}",
                                          "rows": rows, "vectors": vectors.tolist()}))

    def query(self, qvec: np.ndarray, k: int, service: str | None) -> list[dict]:
        if not self.rows:
            raise RuntimeError("Index is empty: run `python rag.py ingest` first")
        scores = self.matrix @ qvec
        order = np.argsort(-scores)
        hits = [dict(self.rows[i], score=float(scores[i])) for i in order
                if service in (None, "general") or self.rows[i]["service"] == service]
        return hits[:k]


class PgVectorStore:
    """Postgres + pgvector: HNSW index, cosine distance, metadata filter in SQL."""

    def __init__(self):
        import psycopg
        from pgvector.psycopg import register_vector
        self.conn = psycopg.connect(PG_DSN, autocommit=True)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self.conn.execute(f"""CREATE TABLE IF NOT EXISTS faq (
            id text PRIMARY KEY, service text NOT NULL, title text, body text,
            embedding vector({EMBED_DIM}))""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS faq_hnsw ON faq USING hnsw (embedding vector_cosine_ops)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS faq_service ON faq (service)")

    def upsert(self, rows: list[dict], vectors: np.ndarray):
        with self.conn.cursor() as cur:
            for r, v in zip(rows, vectors):
                cur.execute("""INSERT INTO faq (id, service, title, body, embedding) VALUES (%s,%s,%s,%s,%s)
                               ON CONFLICT (id) DO UPDATE SET service=EXCLUDED.service, title=EXCLUDED.title,
                               body=EXCLUDED.body, embedding=EXCLUDED.embedding""",
                            (r["id"], r["service"], r["title"], r["body"], v))

    def query(self, qvec: np.ndarray, k: int, service: str | None) -> list[dict]:
        sql = "SELECT id, service, title, body, 1 - (embedding <=> %s) AS score FROM faq"
        params: list = [qvec]
        if service not in (None, "general"):
            sql += " WHERE service = %s"
            params.append(service)
        sql += " ORDER BY embedding <=> %s LIMIT %s"
        params += [qvec, k]
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(id=a, service=b, title=c, body=d, score=float(e)) for a, b, c, d, e in rows]


_store = None


def store():
    global _store
    if _store is None:
        _store = PgVectorStore() if VECTOR_STORE == "pgvector" else MemoryStore()
    return _store


# ================================================================= pipeline
def ingest() -> int:
    vecs = embed([f["body"] for f in FAQS], kind="document", titles=[f["title"] for f in FAQS])
    store().upsert(FAQS, vecs)
    return len(FAQS)


def search(question: str, k: int = 8, service: str | None = None) -> list[dict]:
    return store().query(embed([question], "query")[0], k, service)


def rerank(question: str, hits: list[dict], top_n: int = 3) -> list[dict]:
    if not hits:
        return []
    if RERANK == "bedrock":
        import boto3
        r = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION).rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": question}}],
            sources=[{"type": "INLINE", "inlineDocumentSource": {
                "type": "TEXT", "textDocument": {"text": f"{h['title']}. {h['body']}"}}} for h in hits],
            rerankingConfiguration={"type": "BEDROCK_RERANKING_MODEL", "bedrockRerankingConfiguration": {
                "numberOfResults": min(top_n, len(hits)),
                "modelConfiguration": {"modelArn": RERANK_MODEL_ARN}}})
        return [dict(hits[x["index"]], rerank_score=round(x["relevanceScore"], 4)) for x in r["results"]]
    if RERANK == "lexical":  # offline fallback: BM25-ish overlap on title+body
        q = set(_tokens(question))
        scored = []
        for h in hits:
            d = _tokens(h["title"] + " " + h["body"])
            overlap = sum(1 for t in set(d) if t in q)
            scored.append(dict(h, rerank_score=round(overlap / math.sqrt(len(d) + 1) + 0.1 * h["score"], 4)))
        return sorted(scored, key=lambda h: -h["rerank_score"])[:top_n]
    return hits[:top_n]  # RERANK=none


def retrieve(question: str, service: str | None = None, k: int = 8, top_n: int = 3) -> list[dict]:
    return rerank(question, search(question, k, service), top_n)


ANSWER_SYSTEM = ("Answer ONLY from the numbered context. Cite the source id in square brackets, e.g. [faq-01]. "
                 "If the context does not contain the answer, say you don't know. Max 3 sentences.")


def context_block(hits: list[dict]) -> str:
    return "\n".join(f"[{h['id']}] {h['body']}" for h in hits)


def answer(question: str, hits: list[dict], persona: str = "") -> dict:
    prompt = f"<context>\n{context_block(hits)}\n</context>\n\nQuestion: {question}"
    reply = ask(prompt, system=(persona + " " + ANSWER_SYSTEM).strip(), max_tokens=250)
    return {"answer": reply.text.strip(), "citations": re.findall(r"\[(faq-\d+)\]", reply.text),
            "tokens_in": reply.tokens_in, "tokens_out": reply.tokens_out, "latency_ms": reply.latency_ms}


def check_grounding(question: str, context: str, answer_text: str) -> dict:
    """Is the answer supported by the context (grounding) and on-topic (relevance)?"""
    if GUARDRAIL_ID:
        import boto3
        r = boto3.client("bedrock-runtime", region_name=AWS_REGION).apply_guardrail(
            guardrailIdentifier=GUARDRAIL_ID, guardrailVersion=GUARDRAIL_VERSION, source="OUTPUT",
            content=[{"text": {"text": context, "qualifiers": ["grounding_source"]}},
                     {"text": {"text": question, "qualifiers": ["query"]}},
                     {"text": {"text": answer_text, "qualifiers": ["guard_content"]}}])
        filters = []
        for a in r.get("assessments", []):
            filters += a.get("contextualGroundingPolicy", {}).get("filters", [])
        return {"engine": "bedrock-guardrail", "action": r["action"],
                "grounded": r["action"] != "GUARDRAIL_INTERVENED",
                "scores": {f["type"]: round(f["score"], 3) for f in filters}}
    # Offline fallback: share of answer content words found in the context.
    ans = [t for t in _tokens(re.sub(r"\[faq-\d+\]", "", answer_text)) if len(t) > 2]
    ctx = set(_tokens(context))
    score = sum(1 for t in ans if t in ctx) / max(len(ans), 1)
    return {"engine": "local-overlap", "action": "NONE" if score >= 0.7 else "INTERVENED",
            "grounded": score >= 0.7, "scores": {"GROUNDING": round(score, 3)}}


def rag(question: str, service: str | None = None) -> dict:
    hits = retrieve(question, service)
    out = answer(question, hits)
    out["grounding"] = check_grounding(question, context_block(hits), out["answer"])
    if not out["grounding"]["grounded"]:
        out["answer"] = "I can't confirm that from official Nova City information. Please contact a service centre."
    out["sources"] = [{"id": h["id"], "title": h["title"], "score": round(h.get("rerank_score", h["score"]), 4)}
                      for h in hits]
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ask"
    print(f"embed={EMBED_PROVIDER}:{EMBED_MODEL}:{EMBED_DIM} store={VECTOR_STORE} rerank={RERANK} "
          f"guardrail={'bedrock:' + GUARDRAIL_ID if GUARDRAIL_ID else 'local'} llm={PROVIDER}")
    if cmd == "ingest":
        print(f"ingested {ingest()} documents")
    else:
        q = " ".join(sys.argv[2:]) or "How much does it cost to renew a driving licence?"
        print(json.dumps(rag(q), indent=2))
