"""
Block 1 - one interface over several model providers.

    ask(prompt, system=None)            -> Reply (text + tokens + latency)
    ask_json(prompt, Schema, system)    -> Schema instance (validated structured output)

Providers (LLM_PROVIDER in .env):
    bedrock - Amazon Bedrock Converse API (default model: Nova 2 Lite inference profile)
    gemini  - Google Gemini via google-genai (generate_content)
    mock    - deterministic offline stand-in, used by smoke_test.py (no keys, no cost)

The application never imports a vendor SDK directly: switching provider is a config change.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Type, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

T = TypeVar("T", bound=BaseModel)

PROVIDER = os.getenv("LLM_PROVIDER", "bedrock").lower()
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "us.amazon.nova-2-lite-v1:0")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


@dataclass
class Reply:
    text: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0

    def __str__(self) -> str:
        return (f"[{self.provider}:{self.model}] in={self.tokens_in} out={self.tokens_out} "
                f"{self.latency_ms}ms\n{self.text.strip()}")


# ---------------------------------------------------------------- clients (lazy, cached)
_clients: dict[str, object] = {}


def bedrock_client():
    if "bedrock" not in _clients:
        import boto3
        _clients["bedrock"] = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _clients["bedrock"]


def gemini_client():
    if "gemini" not in _clients:
        from google import genai
        _clients["gemini"] = genai.Client()  # reads GEMINI_API_KEY
    return _clients["gemini"]


# ---------------------------------------------------------------- plain text
def ask(prompt: str, system: str | None = None, provider: str | None = None,
        max_tokens: int = 400, temperature: float | None = None) -> Reply:
    p = (provider or PROVIDER).lower()
    t0 = time.perf_counter()
    if p == "bedrock":
        kwargs = dict(modelId=BEDROCK_MODEL,
                      messages=[{"role": "user", "content": [{"text": prompt}]}],
                      inferenceConfig={"maxTokens": max_tokens})
        if temperature is not None:
            kwargs["inferenceConfig"]["temperature"] = temperature
        if system:
            kwargs["system"] = [{"text": system}]
        r = bedrock_client().converse(**kwargs)
        text = "".join(b.get("text", "") for b in r["output"]["message"]["content"])
        reply = Reply(text, p, BEDROCK_MODEL, r["usage"]["inputTokens"], r["usage"]["outputTokens"])
    elif p == "gemini":
        from google.genai import types
        cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens)
        r = gemini_client().models.generate_content(model=GEMINI_MODEL, contents=prompt, config=cfg)
        u = r.usage_metadata
        reply = Reply(r.text or "", p, GEMINI_MODEL,
                      getattr(u, "prompt_token_count", 0) or 0,
                      getattr(u, "candidates_token_count", 0) or 0)
    elif p == "mock":
        reply = Reply(_mock_text(prompt, system), "mock", "mock-1",
                      len(prompt.split()), 20)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{p}' (use bedrock | gemini | mock)")
    reply.latency_ms = round((time.perf_counter() - t0) * 1000)
    return reply


# ---------------------------------------------------------------- structured output
def ask_json(prompt: str, schema: Type[T], system: str | None = None,
             provider: str | None = None, max_tokens: int = 500) -> T:
    """Return a validated pydantic object.

    bedrock: forced tool use - the model must 'call' a tool whose input schema IS our schema.
    gemini : native JSON mode with response_schema.
    """
    p = (provider or PROVIDER).lower()
    if p == "bedrock":
        tool_name = "emit_" + schema.__name__.lower()
        r = bedrock_client().converse(
            modelId=BEDROCK_MODEL,
            system=[{"text": system}] if system else [],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens},
            toolConfig={
                "tools": [{"toolSpec": {
                    "name": tool_name,
                    "description": f"Return the {schema.__name__} object.",
                    "inputSchema": {"json": schema.model_json_schema()}}}],
                "toolChoice": {"tool": {"name": tool_name}},
            },
        )
        for block in r["output"]["message"]["content"]:
            if "toolUse" in block:
                return schema.model_validate(block["toolUse"]["input"])
        raise RuntimeError("Model did not return the forced tool call")
    if p == "gemini":
        from google.genai import types
        cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens,
                                          response_mime_type="application/json",
                                          response_schema=schema)
        r = gemini_client().models.generate_content(model=GEMINI_MODEL, contents=prompt, config=cfg)
        return schema.model_validate_json(r.text)
    if p == "mock":
        return schema.model_validate(_mock_json(prompt, schema))
    raise ValueError(f"Unknown LLM_PROVIDER '{p}'")


# ---------------------------------------------------------------- offline mock
_SERVICE_WORDS = {
    "residency": ["residency", "visa", "sponsor", "permit renewal", "family", "dependant", "resident permit"],
    "driving": ["driving", "licence", "license", "vehicle", "car", "plate", "fine", "parking"],
}


def mock_service(text: str) -> str | None:
    t = text.lower()
    for service, words in _SERVICE_WORDS.items():
        if any(w in t for w in words):
            return service
    return None


_MOCK_STOP = set("a an the of to for and or is are can i my do does what how when where with in on at be it you".split())


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _MOCK_STOP}


def _mock_text(prompt: str, system: str | None) -> str:
    # If the prompt carries [faq-NN] context blocks, answer with the sentence that best overlaps the question
    # (ties go to the higher-ranked block). Crude on purpose: it only exists to exercise the plumbing.
    blocks = re.findall(r"\[(faq-\d+)\]\s*(.+)", prompt)
    if blocks:
        qm = re.search(r"Question:\s*(.+)", prompt)
        q = _stems(qm.group(1) if qm else "")
        best = max(((len(q & _stems(sent)), -i, fid, sent)
                    for i, (fid, body) in enumerate(blocks)
                    for sent in re.split(r"(?<=[.!?])\s+", body.strip())))
        return f"{best[3]} [{best[2]}]"
    return "Mock reply: " + prompt.strip().splitlines()[-1][:120]


def _mock_json(prompt: str, schema: Type[BaseModel]) -> dict:
    fields = schema.model_fields
    last_line = prompt.strip().splitlines()[-1]
    out: dict = {}
    if "service" in fields:
        service = mock_service(last_line)
        hist = re.search(r"<history>(.*?)</history>", prompt, re.S)
        if service is None and hist:            # follow-up: reuse the latest service in history
            for line in reversed(hist.group(1).strip().splitlines()):
                service = mock_service(line)
                if service:
                    break
        out["service"] = service or "general"
    if "intent" in fields:
        ll = last_line.lower()
        wants_now = re.search(r"\b(apply|submit|book)\b", ll) or (
            "renew" in ll and re.search(r"\b(now|today|please)\b", ll))
        out["intent"] = "apply" if wants_now else "question"
    if "urgency" in fields:
        out["urgency"] = "high" if re.search(r"urgent|today|expired|tomorrow", last_line.lower()) else "normal"
    if "summary" in fields:
        out["summary"] = last_line[:80]
    for name, f in fields.items():
        out.setdefault(name, f.default if f.default is not None else "")
    return out


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "In two sentences, what is a context window?"
    providers = [p.strip() for p in os.getenv("COMPARE", PROVIDER).split(",")]
    for prov in providers:
        print(ask(q, system="You are a concise solutions architect.", provider=prov), "\n")
