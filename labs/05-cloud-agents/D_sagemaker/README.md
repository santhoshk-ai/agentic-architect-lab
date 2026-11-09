# Block D: SageMaker fine-tuning basics (LoRA on Llama 3.2 1B), 30–60 min

**Covers:** Amazon SageMaker fine-tuning. If the G5 quota is 0, this block ends at **Partial**: quota checked, data and job prepared, concepts explained.

## Concept: when to fine-tune (rarely) vs RAG vs prompting
| Need | First choice | Why |
|---|---|---|
| Model lacks *facts* (policies, fees) | **RAG** (labs/03, 04) | Knowledge changes; re-indexing is cheap, retraining isn't; citations |
| Model needs a *format/style/behaviour* it can't reach with prompting | **Fine-tune (LoRA)** | e.g. always rewrite formal circulars in plain English, or domain tone in Arabic |
| Model needs a few rules | **Prompt + few-shot** | Cheapest, versionable (Block E) |

- **LoRA:** freeze the base weights and train small low-rank adapters (`lora_r`, `lora_alpha`). Faster and cheaper, and you can keep several adapters per task.
- **Training job vs endpoint:** a job is batch GPU billed while it runs, then gone. An endpoint is an always-on GPU billed hourly until deleted, which is where lab bills explode. In OTT terms, a job is a transcoding batch and an endpoint is an origin server you forgot to stop.
- **Licence:** Llama needs `accept_eula=true`. Mention licensing and model provenance in any government answer.

## Steps
1. `python quota_check.py` (main venv). It needs ≥1 on `ml.g5.2xlarge for training job usage`, plus `ml.g5.xlarge for endpoint usage` if you want `--deploy`. If they're 0, request the increase now (it can take time), write "Partial: quota pending" in results.md, and go to step 4.
2. Look at the data: `head -3 data/train.jsonl`, `cat data/template.json`. There are 36 synthetic formal→plain rewrites (training) and 4 held out. Note: the template's `{instruction}`/`{context}`/`{response}` placeholders must match the JSONL keys.
3. Separate venv: `python -m venv .venv-sm && source .venv-sm/bin/activate && pip install -r requirements-sm.txt`. Set `SAGEMAKER_ROLE_ARN` in `../.env`.
   - `python finetune_lora.py --run` trains only. It prints `TRAINING DONE in N s` and the job name. Expect ~10–20 min including instance startup.
   - Optional: `python finetune_lora.py --run --deploy` also compares OUT vs REF on the 4 holdout rows, then **deletes the endpoint** in `finally`.
4. Write 5 lines in results.md: job duration, billable seconds (SageMaker console → Training jobs → job), whether outputs follow the plain-English style, and why RAG would still be needed for fee changes.
5. **Teardown check:** `aws sagemaker list-endpoints --region us-east-1` should return `[]`. Optionally delete `s3://<default bucket>/agentlab/` and the model artifacts.

## Common errors
| Symptom | Fix |
|---|---|
| `ResourceLimitExceeded` | Quota 0: request an increase; record Partial meanwhile |
| `CapacityError: Unable to provision requested ML compute capacity` | Retry later, or try `--instance ml.g5.4xlarge` / another Region (per the AWS blog) |
| EULA / access error | `environment={"accept_eula": "true"}` is set; check JumpStart model access in the console |
| `KeyError` in template | JSONL keys must match template placeholders |

## Done when
- [ ] Quota checked and recorded (Partial), **or** training job completed with duration and billable seconds recorded (Hands-on)
- [ ] You can explain LoRA vs full fine-tune vs RAG in 60 seconds with one government example
- [ ] `list-endpoints` returns empty

**Cost:** you pay G5 per-second billing during the training job (minutes for this data size), plus the endpoint per hour **only** while it exists. Check SageMaker pricing for your Region before `--deploy`.
