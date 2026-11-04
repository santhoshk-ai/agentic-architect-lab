# Results: labs/04-bedrock-kb

Run date: 2026-11-04. Region us-east-1. Embeddings `amazon.titan-embed-text-v2:0`, generation `us.amazon.nova-2-lite-v1:0`, vector store S3 Vectors. Numbers below are observed, not expected.

## 1. Embeddings (embed_cosine.py)

`dims=512 texts=10 tokens=171 time=4685 ms`, norm of first vector 1.0000 (`normalize=True`).

Query: *"My visa runs out next month. When can I extend it?"*

| Rank | Cosine | Text |
|---|---|---|
| 1 | 0.3075 | You can renew your residence permit online up to 30 days before it expires… |
| 2 | 0.1489 | Driving licences can be renewed up to 90 days before they expire. |
| 3 | 0.1068 | Refunds for rejected applications arrive within 14 working days. |
| 4 | 0.1021 | Parents can be sponsored when the sponsor earns at least 18,000 NCD a month… |
| 5 | 0.0834 | Mix flour, eggs and milk, then rest the batter for 20 minutes. |
| 6 | 0.0706 | The football final will be played on Saturday evening. |
| 7 | 0.0440 | A 25% discount applies when a traffic fine is paid within 30 days. |
| 8 | 0.0414 | Customer Happiness Centres open from 7:30 to 20:00, Monday to Saturday… |
| 9 | 0.0301 | Home-based business licences cost 750 NCD per year. |
| 10 | 0.0211 | Parking in a loading bay costs 300 NCD. |

Pairwise: cos(residence renew, licence renew) = 0.2954; cos(residence renew, pancake recipe) = -0.0144.

Why the top match won:
- Meaning, not keywords: the query and the winner share no content words (visa ≠ residence permit, runs out ≠ expires, extend ≠ renew), yet it scores 2x the runner-up (0.31 vs 0.15). The model maps both to "renew a residency document before expiry".
- Rank 2 is the same *pattern* (renew before expiry) on the wrong document type, so the rank-1/rank-2 gap is the margin between "right concept, right subject" and "right concept, wrong subject". On a real corpus that gap is the signal to watch: a small gap means a metadata filter or re-ranker is needed to separate them.
- Absolute scores are low (top 0.31) and off-topic texts (pancakes 0.08, football 0.07) outrank some on-domain ones (parking 0.02). Cosine is only meaningful as a ranking, not as an absolute relevance threshold.

`max |cosine - dot|` = 2.98e-08 → what that means for the choice of distance metric:
- Titan V2 with `normalize=True` returns unit vectors, so cosine and dot product give the same ranking (difference is float noise). Dot product is cheaper, so either metric is fine for the index. Without normalisation (norm of text 1 = 0.7221) dot product would mix vector length into the score and the metrics would diverge.

## 2. Retrieve vs RetrieveAndGenerate (compare_kb.py, fixed chunking, k=5)

| Question | Retrieve top-3 sources | hit@3 | RAG cites | Retrieve ms | RAG ms |
|---|---|---|---|---|---|
| How early can I renew my residence permit and what do I need? | residency-permits.md ×3 (0.792, 0.749, 0.728) | True | residency-permits.md | 1460 | 2022 |
| What salary do I need to sponsor my parents? | family-sponsorship.md ×3 (0.778, 0.725, 0.648) | True | family-sponsorship.md | 709 | 2142 |
| How do I dispute a parking fine? | vehicles-and-fines.md ×2, residency-permits.md (0.698, 0.631, 0.616) | True | vehicles-and-fines.md | 1689 | 1783 |
| Do electric cars pay the vehicle registration fee? | vehicles-and-fines.md ×2, driving-licence.md (0.72, 0.627, 0.602) | True | vehicles-and-fines.md | 669 | 1669 |
| How much is a fishing licence in Nova City? | business-licensing.md, driving-licence.md, vehicles-and-fines.md (0.773, 0.727, 0.727) | trap | none | 611 | 1903 |

Out-of-corpus trap (fishing licence), RAG answer and citations:
- Answer: "The search results do not mention anything about fishing licenses in Nova City. The provided information covers business licenses, driving licenses, vehicle registration, residence permits, and traffic fines…" Citations: none. The managed generator correctly declined.
- Retrieve alone gave no such signal: the trap's top score (0.773) is higher than two real hits (parking 0.698, EV 0.72). A score threshold cannot separate in-corpus from out-of-corpus questions; the refusal has to come from the generation step (or a grounding check).

Metadata filter demo ("How early can I renew?"):
- no filter → residency-permits.md, business-licensing.md, driving-licence.md
- service=driving → driving-licence.md, vehicles-and-fines.md, driving-licence.md (both documents tagged `service=driving`; residency and business are excluded)

When I would use Retrieve (own prompt/guardrail) vs RetrieveAndGenerate (managed):
- RetrieveAndGenerate: fast path for a single-turn, cited Q&A where the managed prompt is acceptable. It added 0.1-1.4 s over Retrieve here and handled the trap well with no extra code.
- Retrieve: when I need my own prompt, a grounding/guardrail check, re-ranking, multi-tenant filters injected per caller, or to feed chunks into an agent/tool loop (as in lab 03). Retrieve also exposes scores and sources for evaluation.

## 3. Chunking comparison (chunking_compare.py, k=3)

| Strategy | hit@3 | doc@3 | Avg chunk words | Results returned | Avg retrieve ms | Ingest s |
|---|---|---|---|---|---|---|
| fixed (300, 20%) | 9/10 | 9/10 | 191 | 30/30 | 747 | 22 |
| semantic (300, 95th pct) | 9/10 | 9/10 | 150 | 30/30 | 611 | 32 |
| hierarchical (1500/300) | 9/10 | 9/10 | 430 | 17/30 | 630 | 22 |

Per-question matrix (rank of the answer phrase):

| Question | fixed | semantic | hierarchical |
|---|---|---|---|
| How early can I renew my residence permit? | 2 | 1 | 1 |
| How early can I renew my driving licence? | 3 | 1 | 2 |
| What salary do I need to sponsor my mother and father? | 1 | 1 | 1 |
| How much is the deposit for bringing my parents to live with me? | 1 | 1 | 1 |
| What is the daily fine once the grace period for my expired residence permit ends? | 1 | 1 | 1 |
| Is there a discount if I pay a traffic fine early? | 1 | 2 | 1 |
| How much does it cost to transfer a used car I bought? | 1 | 1 | 1 |
| I write software from my apartment with no clients visiting. What does that licence cost per year? | 1 | 1 | 1 |
| How long does a refund take if my application is rejected? | 2 | 2 | 2 |
| Which sign-in level do I need to renew my permit? | - | - | - |

Which chunking won and why (number question vs two-paragraph question):
- No strategy won on hit@3 (9/10 each). On rank, semantic and hierarchical tie (sum of ranks 11) ahead of fixed (13). The difference is entirely Q1/Q2, the near-duplicate "renew up to N days before it expires" pair: fixed-size chunks blend surrounding text, so the residence and driving sentences look alike and fixed ranked the right one 2nd/3rd; semantic chunks isolate the sentence and put it 1st.
- The designed separators did not separate: Q3 (salary figure one paragraph after "parents") and Q8 ("home-based" defined in section 1, priced in section 2) were rank 1 for every strategy. Each circular is ~550 tokens, so a 300-token chunk already spans the adjacent paragraph and a 1,500-token parent is the whole document. The corpus is too small for boundary effects to show.
- Shared miss, Q10 (sign-in level): every strategy returned only residency-permits.md. The answer ("Level 2 is required for any transaction that changes legal status, such as renewing a permit") lives in nova-id-and-payments.md, while "renew my permit" pulls strongly toward the residency document. This is a retrieval-intent problem, not a chunking problem: it needs query rewriting, a higher k, or hybrid/keyword search on "sign-in level".
- Hierarchical returned 17/30 results because children sharing a parent collapse into one result, and avg chunk words jumps to 430 (whole documents). Same accuracy, but more context per answer: ~730 words per question (430 × 1.7 results) vs ~570 fixed and ~450 semantic.
- Semantic was fastest to retrieve (611 ms) but slowest to ingest (32 s vs 22 s): it pays an embedding pass at ingest time to find breakpoints.

What I would choose for a government policy corpus, and how I would change it later (chunking is immutable per data source → new data source + re-ingest + eval before cutover):
- Start with semantic chunking plus metadata (`service`, `effective_date`, `circular`) used as filters: it ranked near-duplicate policy clauses correctly and keeps chunks small and citable. Consider hierarchical for long circulars where an answer spans sections, accepting the larger context cost.
- To change strategy: create a new data source (and index) with the new chunking config, ingest in parallel, re-run this eval set (plus cross-document questions like Q10) against both, and switch traffic only when the new one matches or beats the old; then delete the old data source.

## 4. Teardown

- [x] `list-knowledge-bases` empty for the lab (verified 2026-11-04: 0 KBs with prefix `agentic-lab04`)
- [x] `list-vector-buckets` empty for the lab (verified 2026-11-04: 0 vector buckets; data bucket and IAM role also gone)
