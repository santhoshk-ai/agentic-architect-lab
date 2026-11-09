# AgentCore Runtime MCP server (MCP SDK v1 per AWS runtime-mcp doc). Synthetic Nova City data only.
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(host="0.0.0.0", stateless_http=True)   # Runtime contract: 0.0.0.0:8000/mcp

FEES = {"driving_licence_renewal": 300, "residency_renewal": 500, "trade_licence_renewal": 1200}  # NCD, synthetic
APPS = {"APP-1001": "SUBMITTED", "APP-1002": "APPROVED", "APP-1003": "NEEDS_DOCUMENTS"}

@mcp.tool()
def get_service_fee(service: str) -> dict:
    """Fee in Nova City dollars (NCD). service: driving_licence_renewal | residency_renewal | trade_licence_renewal"""
    if service not in FEES:
        return {"error": f"unknown service '{service}'", "valid": list(FEES)}
    return {"service": service, "fee_ncd": FEES[service], "source": "fee-schedule-v3 (synthetic)"}

@mcp.tool()
def get_application_status(application_id: str) -> dict:
    """Status of a Nova City application, e.g. APP-1002."""
    return {"application_id": application_id, "status": APPS.get(application_id, "NOT_FOUND")}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
