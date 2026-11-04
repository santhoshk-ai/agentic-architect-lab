# Lab 04: Bedrock Knowledge Bases, managed RAG and chunking

Week 2 (Mon–Wed rows) in one folder:

| Day | Question this lab answers | Script |
|---|---|---|
| Mon | What is an embedding, and why did the top match win? | `embed_cosine.py` |
| Tue | What does a *managed* RAG pipeline give me: Retrieve vs RetrieveAndGenerate, citations, refusal on out-of-corpus questions | `setup_kb.py`, `compare_kb.py` |
| Wed | How much does the chunking strategy change retrieval? Fixed vs semantic vs hierarchical, plus metadata filters | `chunking_compare.py` |

The corpus is six synthetic "Nova City Services" policy circulars (residency, family sponsorship, driving, vehicles and fines, business licences, ID and payments). It is fictional on purpose, so every expected answer is known and nothing is confidential.

## Architecture

```
corpus/*.md + *.metadata.json
        │  upload
        ▼
S3 data bucket ──► Bedrock KB data source (chunking strategy fixed at creation)
                         │ ingestion job: parse → chunk → embed (Titan Text Embeddings V2, 1024 d)
                         ▼
                 S3 Vectors index (one per strategy, cosine)
                         │
      Retrieve ◄─────────┤────────► RetrieveAndGenerate
  (chunks + scores)      │         (answer + citations, Nova 2 Lite via us. inference profile)
                         ▼
               metadata filter: service = residency | driving | business | general
```

Why S3 Vectors rather than OpenSearch Serverless (what the AWS workshop notebooks use): no minimum OCU charge, so three KBs can stay up for an afternoon for cents. Trade-off: semantic search only (no hybrid), 2 KB filterable-metadata limit, and very large hierarchical parent chunks are not recommended. Know both for interviews.

## Prerequisites

- AWS account, CLI profile with permissions for: `bedrock:*KnowledgeBase*`, `bedrock:*DataSource*`, `bedrock:*IngestionJob*`, `bedrock:Retrieve`, `bedrock:RetrieveAndGenerate`, `bedrock:InvokeModel`, `s3:*` on the lab buckets, `s3vectors:*`, `iam:CreateRole/PutRolePolicy/GetRole/PassRole/DeleteRole/DeleteRolePolicy`, `sts:GetCallerIdentity`.
- Region `us-east-1`.
- Model access: Amazon Titan Text Embeddings V2 and Amazon Nova 2 Lite are enabled by default in most accounts. If a call returns `AccessDeniedException ... model`, enable the model in the Bedrock console.
- Python 3.11+.

## Setup

```bash
cd labs/04-bedrock-kb
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # adjust AWS_PROFILE if needed
python smoke_test.py                                   # offline, expect ALL PASS
aws sts get-caller-identity                            # confirm the right account
```

## Run order

### 1. Embeddings by hand (Mon, ~10 min, < $0.01)

```bash
python embed_cosine.py
python embed_cosine.py "My son is 24, can I still keep him on my residency?"
```

Expected: `dims=512`, norm 1.0000, the residence-permit sentence ranked first for the default query even though it shares almost no words with it ("visa runs out" vs "permit expires"). `max |cosine - dot|` is close to 0 because Titan V2 returns unit vectors. The two "renew" sentences score much closer to each other than to the pancake recipe.

Write in results.md: why the top match won (meaning, not keywords) and what the score gap between rank 1 and rank 2 tells you.

### 2. Baseline Knowledge Base (Tue, ~5 min)

```bash
python setup_kb.py
```

Expected output, in order: data bucket created, `uploaded 12 corpus files`, vector bucket, `idx-fixed`, role (15 s wait), `KB active`, data source `FIXED_SIZE`, `ingestion COMPLETE ... scanned=6 indexed=6 failed=0`, then `READY kb_id=...`.

### 3. Retrieve vs RetrieveAndGenerate (Tue, ~5 min)

```bash
python compare_kb.py
```

Expected:
- the 4 in-corpus questions retrieve the right file first, `hit@3=True`;
- RetrieveAndGenerate answers with citations to the same file;
- **the fishing-licence trap**: RetrieveAndGenerate should say it cannot find the answer, and citations should be `NONE`. If it answers anyway, that is the finding: write it down;
- filter demo: "How early can I renew?" without a filter mixes residency and driving; with `service=driving` only driving documents come back.

Copy the printed tables into results.md.

### 4. Chunking comparison (Wed, ~15–20 min, mostly ingestion)

```bash
python chunking_compare.py
```

This reuses the fixed KB and creates two more (semantic, hierarchical), each with its own index, then runs the 10 questions in `questions.json` at k=3. All three KBs stay up so you can probe them.

Output:
- **hit@3**: the expected answer phrase is inside one of the 3 chunks returned;
- **doc@3**: the right document was returned, even if the phrase was cut off. `doc@3` > `hit@3` means the chunk boundary split the answer;
- **avg chunk words**: hierarchical returns the 1,500-token parents; each circular is ~550 tokens, so a parent is the whole document and this number jumps;
- **results returned**: hierarchical often returns fewer than 30, because children that share a parent collapse into one result;
- a per-question matrix showing the rank of the phrase per strategy. The rows where strategies disagree are your write-up.

Questions designed to separate the strategies:
- Q3 (parents' salary): the salary figure sits in the paragraph *after* the one that mentions parents;
- Q8 (software from home): "home-based" is defined in section 1, its price is in section 2;
- Q1 vs Q2: near-identical "renew up to N days before it expires" sentences in two documents.

Probe one KB directly in the console (Knowledge Bases → Test) to see the chunks.

### 5. Teardown (same day)

```bash
python teardown.py --dry-run
python teardown.py
aws bedrock-agent list-knowledge-bases --region us-east-1
aws s3vectors list-vector-buckets --region us-east-1
```

## Cost (us-east-1, check the pricing pages before relying on these)

- Titan Text Embeddings V2: the corpus is ~3,000 tokens (6 docs × ~400 words); 3 ingestions + queries is well under $0.01.
- Semantic chunking makes extra embedding calls during ingestion: still cents at this size.
- Nova 2 Lite for 5 RetrieveAndGenerate calls: under $0.01.
- S3 Vectors storage and queries for a few hundred vectors: negligible.
- No OpenSearch Serverless OCUs. That is the main saving versus the workshop notebooks.

## Common errors

| Error | Fix |
|---|---|
| `ValidationException ... role` on create_knowledge_base | IAM propagation; the script retries 5×. If it persists, re-run `setup_kb.py`. |
| Ingestion `failed>0`, message about metadata size | Non-filterable keys missing on the index. Run teardown and setup again (the index is created with them). |
| `AccessDeniedException` on RetrieveAndGenerate | Your user lacks `bedrock:InvokeModel` on the Nova inference profile, or the model is not enabled. Try `GEN_MODEL_ID=amazon.nova-lite-v1:0` to isolate. |
| `ConflictException` during ingestion | A sync is already running; wait and re-run. |
| All `hit@3` 0 after you edit questions | The `expect` phrase must be copied exactly from the corpus; `python smoke_test.py` checks it. |
| `UnknownServiceError: s3vectors` | Old boto3: `pip install -U boto3`. |

## Done when

- [ ] `embed_cosine.py` output pasted, with one paragraph on why the top match won.
- [ ] `compare_kb.py` table: 4/4 in-corpus hits with citations; trap behaviour recorded; filter demo recorded.
- [ ] `chunking_compare.py` table + per-question matrix, and a "which chunking won and why" paragraph.
- [ ] `teardown.py` run; both list commands empty.

## Files

| File | Purpose |
|---|---|
| `config.py` | Region, model IDs, the three chunking configurations |
| `kb_lib.py` | Idempotent provisioning: buckets, S3 Vectors index, IAM role, KB, data source, ingestion |
| `embed_cosine.py` | Titan V2 embeddings + numpy cosine |
| `setup_kb.py` | Baseline (fixed-size) KB |
| `compare_kb.py` | Retrieve vs RetrieveAndGenerate, citations, trap, metadata filter |
| `chunking_compare.py` | Three strategies × 10 questions |
| `teardown.py` | Removes everything in `state.json` |
| `smoke_test.py` | Offline checks: corpus/answers consistency, scoring logic |
| `corpus/` | Six synthetic circulars + metadata sidecars |
| `questions.json`, `compare_questions.json` | Eval sets (exact answer phrases) |
| `results.md` | Your observed numbers |

`state.json` and `.env` are git-ignored (they hold IDs and ARNs).
