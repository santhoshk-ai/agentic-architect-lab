"""Same triage task on three clouds: Gemini (Google Cloud, ADC), Nova 2 Lite (Bedrock Converse), gpt-5-mini (Foundry).

Learning points: one interface (ask) over three auth models (ADC / IAM SigV4 / Entra ID token), three billing
units and three latency profiles. Each call is logged to ../usage.jsonl -> compare in common/usage.py.
Closes the Fri 30 Oct syllabus Done-when ("one interface, multiple providers") with Azure added.
"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.usage import log_call  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SYSTEM = ("Classify the citizen message. Reply with JSON only: "
          '{"intent": "driving|residency|trade|complaint|other", "urgent": true|false}')
MESSAGES = ["My driving licence expires tomorrow and I travel on Friday, can I renew online?",
            "I want to complain, your office closed early and nobody answered the phone.",
            "How do I add a new activity to my trade licence?"]


def ask_gemini(text):
    from google import genai
    proj, loc = os.environ["GOOGLE_CLOUD_PROJECT"], os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    try:
        c = genai.Client(enterprise=True, project=proj, location=loc)
    except TypeError:  # older SDKs
        c = genai.Client(vertexai=True, project=proj, location=loc)
    model = os.environ["GEMINI_MODEL"]
    r = c.models.generate_content(model=model, contents=f"{SYSTEM}\n\nMessage: {text}")
    u = r.usage_metadata
    return model, r.text, u.prompt_token_count or 0, u.candidates_token_count or 0


def ask_nova(text):
    import boto3
    model = os.getenv("NOVA_LITE_PROFILE", "us.amazon.nova-2-lite-v1:0")
    r = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1")).converse(
        modelId=model, system=[{"text": SYSTEM}], messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"maxTokens": 200})
    return model, r["output"]["message"]["content"][0]["text"], r["usage"]["inputTokens"], r["usage"]["outputTokens"]


def ask_foundry(text):
    from first_call import client
    dep = os.getenv("FOUNDRY_DEPLOYMENT", "gpt-5-mini")
    r = client().responses.create(model=dep, instructions=SYSTEM, input=text, max_output_tokens=800)
    return dep, r.output_text, r.usage.input_tokens, r.usage.output_tokens


def parse(txt):
    s = txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {"unparsed": txt[:80]}


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    only = sys.argv[1:] or ["gemini", "nova", "foundry"]
    fns = {"gemini": ask_gemini, "nova": ask_nova, "foundry": ask_foundry}
    for name in only:
        for m in MESSAGES:
            t0 = time.time()
            try:
                model, out, i, o = fns[name](m)
            except Exception as e:  # keep going: one provider down must not stop the comparison
                print(f"{name:8} ERROR {type(e).__name__}: {str(e)[:150]}")
                break
            ms = int((time.time() - t0) * 1000)
            log_call(source="C_three_providers", model=model, input_tokens=i, output_tokens=o, latency_ms=ms)
            print(f"{name:8} {ms:6} ms in={i:4} out={o:4} {parse(out)}")
