"""LoRA instruction-tuning of Llama 3.2 1B with SageMaker JumpStart (pattern from the AWS ML blog
"Fine-tune Meta Llama 3.2 text generation models ... using Amazon SageMaker JumpStart").

Learning points:
- Fine-tuning changes *behaviour/style* (here: formal circular -> plain English). It is NOT how you add knowledge; that's RAG.
- LoRA trains small adapter matrices (r, alpha) instead of all weights, so it's cheaper and faster, and the base model is untouched.
- Training job = ephemeral GPU, billed per second while it runs. Endpoint = always-on GPU, billed per hour until DELETED.

Guarded: does nothing without --run. Endpoint only with --deploy, and it's deleted in `finally`.
  python finetune_lora.py --run                 # train only (needs ml.g5.2xlarge training quota >= 1)
  python finetune_lora.py --run --deploy        # train, deploy, compare base-style vs tuned on holdout, delete endpoint
"""
import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parent / ".env")
MODEL_ID = "meta-textgeneration-llama-3-2-1b"


def main(a):
    import sagemaker
    from sagemaker.jumpstart.estimator import JumpStartEstimator

    sess = sagemaker.Session()
    role = os.environ["SAGEMAKER_ROLE_ARN"]
    train_s3 = sess.upload_data(str(HERE / "data"), key_prefix=f"agentlab/llama32-lora/{int(time.time())}")
    print("training data:", train_s3)
    est = JumpStartEstimator(model_id=MODEL_ID, role=role, environment={"accept_eula": "true"},  # Meta licence
                             instance_type=a.instance, disable_output_compression=True)
    est.set_hyperparameters(instruction_tuned="True", epoch=str(a.epochs), max_input_length="512",
                            lora_r="8", lora_alpha="32", per_device_train_batch_size="2")
    t0 = time.time()
    est.fit({"training": train_s3}, logs=True)
    print(f"TRAINING DONE in {int(time.time() - t0)} s -> job {est.latest_training_job.name}")
    print("model artifacts:", est.model_data)
    if not a.deploy:
        print("No endpoint created (cost-safe). Re-run with --deploy to test the tuned model.")
        return
    pred = est.deploy(instance_type="ml.g5.xlarge")
    try:
        tmpl = json.loads((HERE / "data/template.json").read_text())
        for line in (HERE / "data/holdout.jsonl").read_text().splitlines():
            r = json.loads(line)
            prompt = tmpl["prompt"].format(**r)
            out = pred.predict({"inputs": prompt, "parameters": {"max_new_tokens": 80}})
            gen = out.get("generated_text") if isinstance(out, dict) else out[0].get("generated_text")
            print(f"\nIN : {r['context']}\nOUT: {gen.strip()}\nREF: {r['response']}")
    finally:
        pred.delete_model()
        pred.delete_endpoint()
        print("\nendpoint + model deleted")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--instance", default="ml.g5.2xlarge")
    a = ap.parse_args()
    if not a.run:
        print(__doc__)
    else:
        main(a)
