"""Shared settings for labs/04-bedrock-kb. Values come from .env (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

REGION = os.getenv("AWS_REGION", "us-east-1")
PREFIX = os.getenv("LAB_PREFIX", "agentic-lab04")          # lowercase, digits, hyphens

# Embeddings: Titan Text Embeddings V2 (normalised vectors, 256/512/1024 dims)
EMBED_MODEL_ID = os.getenv("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBED_DIMS = int(os.getenv("EMBED_DIMS", "1024"))           # KB index dimension

# Generation for RetrieveAndGenerate: inference profile ID, foundation model ID, or full ARN
GEN_MODEL_ID = os.getenv("GEN_MODEL_ID", "us.amazon.nova-2-lite-v1:0")

CORPUS_DIR = HERE / "corpus"
CORPUS_S3_PREFIX = "corpus/"
STATE_FILE = HERE / "state.json"                           # git-ignored: holds ARNs/IDs

# One KB per chunking strategy, each with its own S3 Vectors index (no cross-contamination)
STRATEGIES = {
    "fixed": {
        "chunkingStrategy": "FIXED_SIZE",
        "fixedSizeChunkingConfiguration": {"maxTokens": 300, "overlapPercentage": 20},
    },
    "semantic": {
        "chunkingStrategy": "SEMANTIC",
        "semanticChunkingConfiguration": {
            "maxTokens": 300, "bufferSize": 0, "breakpointPercentileThreshold": 95},
    },
    "hierarchical": {
        "chunkingStrategy": "HIERARCHICAL",
        "hierarchicalChunkingConfiguration": {
            "levelConfigurations": [{"maxTokens": 1500}, {"maxTokens": 300}],
            "overlapTokens": 60},
    },
}
