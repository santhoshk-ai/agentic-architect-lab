"""Deletes the Block B agent, aliases, Lambda and both IAM roles. Agents have no idle cost, but clean up anyway."""
import json
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
s = json.loads((HERE / "agent_state.json").read_text())
ba = boto3.client("bedrock-agent", region_name=s["region"])
lam = boto3.client("lambda", region_name=s["region"])
iam = boto3.client("iam")

for al in ba.list_agent_aliases(agentId=s["agentId"])["agentAliasSummaries"]:
    if al["agentAliasId"] != "TSTALIASID":
        ba.delete_agent_alias(agentId=s["agentId"], agentAliasId=al["agentAliasId"]); print("deleted alias", al["agentAliasName"])
ba.delete_agent(agentId=s["agentId"], skipResourceInUseCheck=True); print("deleted agent", s["agentId"])
lam.delete_function(FunctionName="nova-agent-tools"); print("deleted lambda")
iam.delete_role_policy(RoleName="nova-agent-service-role", PolicyName="nova-agent-service-role-inline")
iam.delete_role(RoleName="nova-agent-service-role")
iam.detach_role_policy(RoleName="nova-agent-lambda-role", PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
iam.delete_role(RoleName="nova-agent-lambda-role"); print("deleted roles")
(HERE / "agent_state.json").unlink()
print("verify:", [a["agentName"] for a in ba.list_agents()["agentSummaries"]])
