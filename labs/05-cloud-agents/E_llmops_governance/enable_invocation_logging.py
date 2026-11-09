"""Turns on Bedrock model invocation logging (account+Region wide) to CloudWatch Logs, or off with --disable.

LLMOps point: usage.jsonl is *your* view; invocation logging is the *platform's* view of every prompt and response,
including calls you didn't instrument. Government reality: those logs contain citizen data, so retention,
encryption (KMS) and access are governance decisions (see governance.md rows 4 and 7).
"""
import json
import os
import sys

import boto3

REGION = os.getenv("AWS_REGION", "us-east-1")
LG, ROLE = "/agentlab/bedrock-invocations", "agentlab-bedrock-logging-role"
br, logs, iam = boto3.client("bedrock", region_name=REGION), boto3.client("logs", region_name=REGION), boto3.client("iam")
ACCOUNT = boto3.client("sts").get_caller_identity()["Account"]

if "--disable" in sys.argv:
    br.delete_model_invocation_logging_configuration()
    print("invocation logging disabled. Optional cleanup: delete log group", LG, "and role", ROLE)
    sys.exit()

try:
    logs.create_log_group(logGroupName=LG)
except logs.exceptions.ResourceAlreadyExistsException:
    pass
logs.put_retention_policy(logGroupName=LG, retentionInDays=3)  # lab: short retention on purpose
trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
         "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}}}]}
try:
    arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
except iam.exceptions.EntityAlreadyExistsException:
    arn = iam.get_role(RoleName=ROLE)["Role"]["Arn"]
iam.put_role_policy(RoleName=ROLE, PolicyName="write-logs", PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
     "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{LG}:*"}]}))
import time; time.sleep(10)  # IAM propagation
br.put_model_invocation_logging_configuration(loggingConfig={
    "cloudWatchConfig": {"logGroupName": LG, "roleArn": arn}, "textDataDeliveryEnabled": True,
    "imageDataDeliveryEnabled": False, "embeddingDataDeliveryEnabled": False})
print("enabled ->", LG, "| test: run prompt_ab.py, then: aws logs tail", LG, "--since 10m")
print("REMEMBER: python enable_invocation_logging.py --disable  (it is account-wide in this Region)")
