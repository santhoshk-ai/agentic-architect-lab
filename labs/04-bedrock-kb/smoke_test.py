"""Offline checks (no AWS calls): corpus/question consistency, config, scoring logic.

Usage: python smoke_test.py
"""
import json
import os
import py_compile
import sys

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import boto3
from botocore.stub import Stubber

import config as C
import kb_lib as L
import chunking_compare as CC

ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail and not cond else ''}")


def norm(s):
    return " ".join(s.split()).lower()


# 1. every module compiles
for f in ["config.py", "kb_lib.py", "embed_cosine.py", "setup_kb.py", "compare_kb.py",
          "chunking_compare.py", "teardown.py"]:
    try:
        py_compile.compile(str(C.HERE / f), doraise=True)
        check(f"compile {f}", True)
    except py_compile.PyCompileError as e:
        check(f"compile {f}", False, str(e))

# 2. corpus + sidecars
docs = {p.name: p.read_text() for p in C.CORPUS_DIR.glob("*.md")}
check("6 corpus documents", len(docs) == 6, str(list(docs)))
for name in docs:
    side = C.CORPUS_DIR / f"{name}.metadata.json"
    meta = json.loads(side.read_text()) if side.exists() else {}
    check(f"sidecar {side.name}", "service" in meta.get("metadataAttributes", {}))

# 3. every expected phrase exists in its stated document
for qfile in ["questions.json", "compare_questions.json"]:
    qs = json.loads((C.HERE / qfile).read_text())
    for q in qs:
        if q.get("out_of_corpus"):
            hit = any(norm("fishing") in norm(t) for t in docs.values())
            check(f"{qfile}: trap really out of corpus", not hit)
            continue
        check(f"{qfile}: '{q['expect']}' in {q['doc']}", norm(q["expect"]) in norm(docs[q["doc"]]))
check("10 eval questions", len(json.loads((C.HERE / "questions.json").read_text())) == 10)

# 4. config sanity
check("3 chunking strategies", set(C.STRATEGIES) == {"fixed", "semantic", "hierarchical"})
check("embedding dims valid for Titan V2", C.EMBED_DIMS in (256, 512, 1024))
check("inference profile ARN", L.gen_model_arn("111122223333") ==
      f"arn:aws:bedrock:{C.REGION}:111122223333:inference-profile/{C.GEN_MODEL_ID}"
      if C.GEN_MODEL_ID.startswith("us.") else True)

# 5. scoring logic with a stubbed Retrieve
rt = boto3.client("bedrock-agent-runtime", region_name="us-east-1",
                  aws_access_key_id="x", aws_secret_access_key="x")
qs = [{"q": "a", "expect": "18,000 NCD", "doc": "family-sponsorship.md"},
      {"q": "b", "expect": "25% discount applies", "doc": "vehicles-and-fines.md"}]
with Stubber(rt) as st:
    def res(text, doc):
        return {"content": {"text": text}, "score": 0.5,
                "location": {"type": "S3", "s3Location": {"uri": f"s3://b/corpus/{doc}"}}}
    st.add_response("retrieve", {"retrievalResults": [
        res("The minimum monthly salary required is 18,000 NCD, or ...", "family-sponsorship.md")]})
    st.add_response("retrieve", {"retrievalResults": [
        res("Fines can be paid in the app ...", "vehicles-and-fines.md"),
        res("Parking fine 150 NCD", "vehicles-and-fines.md")]})
    rows, stats = CC.evaluate(rt, "KBTEST0001", qs, 3)
check("hit@3 counts phrase hits", stats["hit@3"] == "1/2", str(stats))
check("doc@3 counts right-document hits", stats["doc@3"] == "2/2", str(stats))
check("results_returned shows shrinkage", stats["results_returned"] == "3/6", str(stats))

# 6. repo rule: banned term must not appear anywhere in this folder
banned = "cla" + "ude"
bad = [p.name for p in C.HERE.rglob("*") if p.is_file() and not {".venv", "__pycache__", ".git"} & set(p.parts)
       and banned in (p.name.lower() + p.read_text(errors="ignore").lower())]
check("banned term absent", not bad, str(bad))

print("\nALL PASS" if ok else "\nFAILURES ABOVE")
sys.exit(0 if ok else 1)
