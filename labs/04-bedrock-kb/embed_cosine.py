"""Monday's row: embed 10 short texts with Titan Text Embeddings V2 and compute cosine
similarity yourself in numpy. Explain why the top match won.

Usage: python embed_cosine.py ["your own query"]
"""
import json
import sys
import time

import boto3
import numpy as np

import config as C

DIMS = 512   # Titan V2 accepts 256, 512 or 1024

TEXTS = [
    "You can renew your residence permit online up to 30 days before it expires.",
    "Driving licences can be renewed up to 90 days before they expire.",
    "Parents can be sponsored when the sponsor earns at least 18,000 NCD a month.",
    "A 25% discount applies when a traffic fine is paid within 30 days.",
    "Parking in a loading bay costs 300 NCD.",
    "Home-based business licences cost 750 NCD per year.",
    "Customer Happiness Centres open from 7:30 to 20:00, Monday to Saturday.",
    "Refunds for rejected applications arrive within 14 working days.",
    "The football final will be played on Saturday evening.",
    "Mix flour, eggs and milk, then rest the batter for 20 minutes.",
]
DEFAULT_QUERY = "My visa runs out next month. When can I extend it?"


def embed(rt, text, normalize=True):
    body = json.dumps({"inputText": text, "dimensions": DIMS, "normalize": normalize})
    out = json.loads(rt.invoke_model(modelId=C.EMBED_MODEL_ID, body=body)["body"].read())
    return np.array(out["embedding"], dtype=np.float32), out["inputTextTokenCount"]


def cosine(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    rt = boto3.client("bedrock-runtime", region_name=C.REGION)

    t0 = time.time()
    vecs, tokens = zip(*(embed(rt, t) for t in TEXTS))
    qv, qtok = embed(rt, query)
    ms = round((time.time() - t0) * 1000)
    M = np.vstack(vecs)

    print(f"model={C.EMBED_MODEL_ID} dims={M.shape[1]} texts={len(TEXTS)} "
          f"tokens={sum(tokens) + qtok} time={ms} ms")
    print(f"norm of first vector = {np.linalg.norm(M[0]):.4f} (normalize=True -> 1.0)")
    print(f'\nquery: "{query}"\n')

    scores = [(cosine(qv, v), v @ qv, t) for v, t in zip(M, TEXTS)]
    print("rank  cosine   dot      text")
    for i, (c, d, t) in enumerate(sorted(scores, reverse=True), 1):
        print(f"{i:>4}  {c:.4f}  {d:.4f}  {t[:70]}")

    # unit vectors -> cosine == dot product; this is why vector stores can use either metric
    max_gap = max(abs(c - d) for c, d, _ in scores)
    print(f"\nmax |cosine - dot| = {max_gap:.2e}  (unit vectors, so they are the same ranking)")

    # what does an un-normalised vector look like?
    raw, _ = embed(rt, TEXTS[0], normalize=False)
    print(f"un-normalised norm of text 1 = {np.linalg.norm(raw):.4f}")

    # pairwise similarity between the two "renew" sentences vs an unrelated pair
    print(f"\ncos(residence renew, licence renew) = {cosine(M[0], M[1]):.4f}")
    print(f"cos(residence renew, pancake recipe) = {cosine(M[0], M[9]):.4f}")


if __name__ == "__main__":
    main()
