"""First call to a Foundry deployment with Entra ID (no keys), via the OpenAI SDK against <project>/openai/v1.

Learning points: on Azure the *deployment name* is the model parameter (not the model ID); auth is a bearer token
from DefaultAzureCredential with scope https://ai.azure.com/.default (pattern from Microsoft Learn
"Generate responses", checked 5 Nov 2026). Same Responses API as OpenAI, so the code is portable across both.
"""
import os
import sys
import time
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.usage import log_call  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def client() -> OpenAI:
    base_url = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/") + "/openai/v1"
    return OpenAI(base_url=base_url,
                  api_key=get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default"))


if __name__ == "__main__":
    dep = os.getenv("FOUNDRY_DEPLOYMENT", "gpt-5-mini")
    t0 = time.time()
    r = client().responses.create(model=dep, input="In one sentence: what is a sovereign cloud?", max_output_tokens=800)
    ms = int((time.time() - t0) * 1000)
    print("ANSWER:", r.output_text)
    print("status:", r.status, "| in:", r.usage.input_tokens, "| out:", r.usage.output_tokens, "| ms:", ms)
    log_call(source="C_foundry_first", model=dep, input_tokens=r.usage.input_tokens,
             output_tokens=r.usage.output_tokens, latency_ms=ms)
