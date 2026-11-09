"""Step 1 of every GPU job: do you even have quota? New accounts often have 0 for G5 training/endpoint instances.

Prints the applied quota (or AWS default) for the instances this block uses. Uses only boto3 (main venv is fine).
"""
import os

import boto3

REGION = os.getenv("AWS_REGION", "us-east-1")
WANT = ["ml.g5.2xlarge for training job usage", "ml.g5.xlarge for endpoint usage",
        "ml.g5.2xlarge for endpoint usage"]
sq = boto3.client("service-quotas", region_name=REGION)
found = {}
for page in sq.get_paginator("list_service_quotas").paginate(ServiceCode="sagemaker"):
    for q in page["Quotas"]:
        if q["QuotaName"] in WANT:
            found[q["QuotaName"]] = (q["Value"], q["QuotaCode"])
for name in WANT:
    v = found.get(name)
    if v is None:
        print(f"{name:42} not in applied quotas -> check the default with: aws service-quotas list-aws-default-service-quotas --service-code sagemaker")
    else:
        print(f"{name:42} {v[0]:>5}  ({v[1]})  {'OK' if v[0] >= 1 else 'REQUEST INCREASE'}")
print("\nIf 0: request +1 via Service Quotas console (approval can take hours to days). Mark SageMaker FT = Partial until it runs.")
