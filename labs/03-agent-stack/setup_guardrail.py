"""
Block 2 - create a Bedrock guardrail with contextual grounding + relevance checks (0.7 / 0.7).
Run once, then put the printed GUARDRAIL_ID into .env. Uses the DRAFT version (fine for a lab).

    python setup_guardrail.py          # create
    python setup_guardrail.py delete   # teardown
"""
import os
import sys

import boto3
from dotenv import load_dotenv

load_dotenv()
REGION = os.getenv("AWS_REGION", "us-east-1")
NAME = "nova-city-grounding"
bedrock = boto3.client("bedrock", region_name=REGION)

if len(sys.argv) > 1 and sys.argv[1] == "delete":
    # an empty id hits DELETE /guardrails/ -> 404 UnknownOperation, so fall back to lookup by name
    gid = os.getenv("GUARDRAIL_ID") or next(
        (g["id"] for g in bedrock.list_guardrails()["guardrails"] if g["name"] == NAME), None)
    if not gid:
        sys.exit(f"no guardrail named {NAME} in {REGION} - nothing to delete")
    bedrock.delete_guardrail(guardrailIdentifier=gid)
    print("deleted", gid)
    sys.exit(0)

r = bedrock.create_guardrail(
    name=NAME,
    description="Lab: block answers not grounded in retrieved Nova City FAQs",
    contextualGroundingPolicyConfig={"filtersConfig": [
        {"type": "GROUNDING", "threshold": 0.7},
        {"type": "RELEVANCE", "threshold": 0.7},
    ]},
    blockedInputMessaging="Sorry, I can't help with that request.",
    blockedOutputsMessaging="I can't confirm that from official Nova City information.",
)
print(f"GUARDRAIL_ID={r['guardrailId']}\nGUARDRAIL_VERSION=DRAFT")
