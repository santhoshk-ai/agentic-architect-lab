"""Action-group Lambda for a Bedrock Agent defined with *function details*.

Event (per AWS agents-lambda doc): {messageVersion, agent, inputText, sessionId, actionGroup, function,
parameters: [{name, type, value}], sessionAttributes, promptSessionAttributes}
Response: {messageVersion, response: {actionGroup, function, functionResponse: {responseBody: {TEXT: {body: str}}}}}
Compare with Block A: the Gateway passes tool args as the event and the tool name in client_context.
Same tool, two different integration contracts. That is the lock-in MCP removes.
"""
import hashlib
import json

FEES = {"driving_licence_renewal": 300, "residency_renewal": 500, "trade_licence_renewal": 1200}  # NCD, synthetic
APPS = {"APP-1001": "SUBMITTED", "APP-1002": "APPROVED", "APP-1003": "NEEDS_DOCUMENTS"}


def _do(function: str, p: dict) -> dict:
    if function == "get_service_fee":
        s = p.get("service", "")
        return {"service": s, "fee_ncd": FEES[s]} if s in FEES else {"error": f"unknown service '{s}'", "valid": list(FEES)}
    if function == "get_application_status":
        a = p.get("application_id", "")
        return {"application_id": a, "status": APPS.get(a, "NOT_FOUND")}
    if function == "submit_application":
        ref = "APP-2" + hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:3].upper()
        return {"submitted": True, "reference": ref, "service": p.get("service"), "applicant": p.get("applicant_name")}
    return {"error": f"unknown function {function}"}


def handler(event, context):
    params = {x["name"]: x["value"] for x in event.get("parameters", [])}
    result = _do(event["function"], params)
    print(json.dumps({"function": event["function"], "params": params, "result": result}))  # CloudWatch audit line
    return {"messageVersion": event.get("messageVersion", "1.0"),
            "response": {"actionGroup": event["actionGroup"], "function": event["function"],
                         "functionResponse": {"responseBody": {"TEXT": {"body": json.dumps(result)}}}}}
