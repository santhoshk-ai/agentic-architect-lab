"""Creates a Bedrock Agent (managed orchestration) with a Lambda action group, prepares it and publishes alias v1.

Learning points:
- Managed agent = AWS owns the orchestration loop (ReAct-style prompts). You own instruction, tools, guardrails.
- DRAFT -> prepare -> alias (immutable version). Alias = blue/green pointer, like a CloudFront origin group.
- requireConfirmation=ENABLED on submit_application = built-in human-in-the-loop (agent returns control).
- Model: amazon.nova-pro-v1:0 in-region (Nova 2 Lite does not support Agents per its model card, 5 Nov 2026).
Writes agent_state.json for invoke_agent.py / teardown_agent.py.
"""
import io
import json
import os
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parent / ".env")
REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL = os.getenv("AGENT_MODEL", "amazon.nova-pro-v1:0")
NAME = "nova-city-agent"
STATE = HERE / "agent_state.json"

sts, iam = boto3.client("sts"), boto3.client("iam")
lam = boto3.client("lambda", region_name=REGION)
ba = boto3.client("bedrock-agent", region_name=REGION)
ACCOUNT = sts.get_caller_identity()["Account"]

INSTRUCTION = ("You are the Nova City government services assistant. Use the tools for every fee, status or "
               "submission; never invent fees or references. Before submitting an application make sure you have "
               "the service and the applicant's full name. Reply in at most three sentences.")

FUNCTIONS = [
    {"name": "get_service_fee", "description": "Fee in Nova City dollars (NCD) for a service.",
     "parameters": {"service": {"type": "string", "required": True,
                                "description": "driving_licence_renewal | residency_renewal | trade_licence_renewal"}}},
    {"name": "get_application_status", "description": "Status of an application, e.g. APP-1002.",
     "parameters": {"application_id": {"type": "string", "required": True, "description": "Application ID like APP-1002"}}},
    {"name": "submit_application", "description": "Submit a new application. Has legal effect: needs user confirmation.",
     "parameters": {"service": {"type": "string", "required": True, "description": "Service key"},
                    "applicant_name": {"type": "string", "required": True, "description": "Applicant full name"}},
     "requireConfirmation": "ENABLED"},
]


def role(name: str, trust: dict, inline: dict | None = None, managed: str | None = None) -> str:
    try:
        arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
    if inline:
        iam.put_role_policy(RoleName=name, PolicyName=f"{name}-inline", PolicyDocument=json.dumps(inline))
    if managed:
        iam.attach_role_policy(RoleName=name, PolicyArn=managed)
    return arn


def wait(fn, field, ok, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = fn()[field]
        status = st.get("agentStatus") or st.get("agentAliasStatus")
        if status in ok:
            return status
        if status and "FAILED" in status:
            raise RuntimeError(f"{field} {status}: {st.get('failureReasons')}")
        time.sleep(4)
    raise TimeoutError(field)


def main():
    # 1) Lambda for the action group
    lrole = role("nova-agent-lambda-role",
                 {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                                                          "Action": "sts:AssumeRole"}]},
                 managed="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(HERE / "agent_lambda.py", "agent_lambda.py")
    for attempt in range(6):
        try:
            fn_arn = lam.create_function(FunctionName="nova-agent-tools", Runtime="python3.12", Role=lrole,
                                         Handler="agent_lambda.handler", Code={"ZipFile": buf.getvalue()},
                                         Timeout=15)["FunctionArn"]
            break
        except lam.exceptions.ResourceConflictException:
            fn_arn = lam.get_function(FunctionName="nova-agent-tools")["Configuration"]["FunctionArn"]
            break
        except ClientError as e:
            if "role" in str(e).lower() and attempt < 5:
                print("waiting for IAM role propagation..."); time.sleep(10); continue
            raise
    print("lambda:", fn_arn)

    # 2) Agent service role: least privilege = invoke ONE model
    arole = role("nova-agent-service-role",
                 {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
                   "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT},
                   "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:agent/*"}}}]},
                 inline={"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "bedrock:InvokeModel",
                         "Resource": f"arn:aws:bedrock:{REGION}::foundation-model/{MODEL}"}]})
    print("agent role:", arole)

    # 3) Agent (retry while the new role propagates)
    for attempt in range(6):
        try:
            agent = ba.create_agent(agentName=NAME, foundationModel=MODEL, instruction=INSTRUCTION,
                                    agentResourceRoleArn=arole, idleSessionTTLInSeconds=600,
                                    description="Labs 05 block B: managed agent with confirmation step")["agent"]
            break
        except ClientError as e:
            if attempt < 5 and e.response["Error"]["Code"] in ("ValidationException", "AccessDeniedException"):
                print("retrying create_agent:", e.response["Error"]["Message"][:120]); time.sleep(10); continue
            raise
    aid = agent["agentId"]
    print("agent:", aid, agent["agentArn"])
    wait(lambda: ba.get_agent(agentId=aid), "agent", {"NOT_PREPARED", "PREPARED"})

    # 4) Allow ONLY this agent to invoke the Lambda
    lam.add_permission(FunctionName="nova-agent-tools", StatementId="allow-nova-agent", Action="lambda:InvokeFunction",
                       Principal="bedrock.amazonaws.com", SourceArn=agent["agentArn"], SourceAccount=ACCOUNT)

    # 5) Action group on DRAFT, prepare, alias v1
    ba.create_agent_action_group(agentId=aid, agentVersion="DRAFT", actionGroupName="nova-services",
                                 actionGroupExecutor={"lambda": fn_arn}, functionSchema={"functions": FUNCTIONS},
                                 actionGroupState="ENABLED")
    ba.prepare_agent(agentId=aid)
    print("prepare:", wait(lambda: ba.get_agent(agentId=aid), "agent", {"PREPARED"}))
    alias = ba.create_agent_alias(agentId=aid, agentAliasName="v1")["agentAlias"]
    print("alias v1:", wait(lambda: ba.get_agent_alias(agentId=aid, agentAliasId=alias["agentAliasId"]),
                            "agentAlias", {"PREPARED"}), alias["agentAliasId"])
    STATE.write_text(json.dumps({"agentId": aid, "agentArn": agent["agentArn"], "aliasId": alias["agentAliasId"],
                                 "lambda": fn_arn, "region": REGION, "model": MODEL}, indent=2))
    print(f"saved {STATE.name}. Next: python invoke_agent.py")


if __name__ == "__main__":
    main()
