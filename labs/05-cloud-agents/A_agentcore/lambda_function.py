# Gateway Lambda target: Gateway passes tool args as the event and the tool name in client context.
FEES = {"driving_licence_renewal": 300, "residency_renewal": 500, "trade_licence_renewal": 1200}
APPS = {"APP-1001": "SUBMITTED", "APP-1002": "APPROVED", "APP-1003": "NEEDS_DOCUMENTS"}

def handler(event, context):
    full = context.client_context.custom["bedrockAgentCoreToolName"]   # e.g. NovaTools___get_service_fee
    tool = full.split("___", 1)[-1]
    if tool == "get_service_fee":
        s = event.get("service", "")
        return {"service": s, "fee_ncd": FEES[s]} if s in FEES else {"error": f"unknown service '{s}'", "valid": list(FEES)}
    if tool == "get_application_status":
        a = event.get("application_id", "")
        return {"application_id": a, "status": APPS.get(a, "NOT_FOUND")}
    return {"error": f"unknown tool {tool}"}
