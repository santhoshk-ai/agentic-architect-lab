"""Offline smoke test: no cloud calls. Run from labs/05-cloud-agents:  python smoke_test.py"""
import importlib.util
import json
import os
import py_compile
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (f" ({detail})" if detail else ""))
    ok &= bool(cond)


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 1) every python file compiles
files = [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "NovaMcp" not in p.parts]
bad = []
for p in files:
    try:
        py_compile.compile(str(p), doraise=True)
    except py_compile.PyCompileError as e:
        bad.append(f"{p.name}: {e}")
check(f"compile {len(files)} python files", not bad, "; ".join(bad))

# 2) json files parse
for p in ROOT.rglob("*.json"):
    if ".venv" in p.parts or "NovaMcp" in p.parts:
        continue
    try:
        json.loads(p.read_text())
        check(f"json {p.relative_to(ROOT)}", True)
    except json.JSONDecodeError as e:
        check(f"json {p.relative_to(ROOT)}", False, str(e))
for line in (ROOT / "D_sagemaker/data/train.jsonl").read_text().splitlines():
    r = json.loads(line)
    json.loads((ROOT / "D_sagemaker/data/template.json").read_text())["prompt"].format(**r)
check("D template placeholders match train.jsonl keys", True)

# 3) Gateway Lambda handler (Block A)
gw = load(ROOT / "A_agentcore/lambda_function.py")
ctx = types.SimpleNamespace(client_context=types.SimpleNamespace(custom={"bedrockAgentCoreToolName": "NovaLambda___get_service_fee"}))
check("A lambda fee", gw.handler({"service": "residency_renewal"}, ctx) == {"service": "residency_renewal", "fee_ncd": 500})
ctx.client_context.custom["bedrockAgentCoreToolName"] = "NovaLambda___get_application_status"
check("A lambda status", gw.handler({"application_id": "APP-1002"}, ctx)["status"] == "APPROVED")
check("A tools.json names match handler", {t["name"] for t in json.loads((ROOT / "A_agentcore/tools.json").read_text())}
      == {"get_service_fee", "get_application_status"})

# 4) Bedrock Agent Lambda handler (Block B)
ag = load(ROOT / "B_bedrock_agent/agent_lambda.py")
ev = {"messageVersion": "1.0", "actionGroup": "nova-services", "function": "get_service_fee",
      "parameters": [{"name": "service", "type": "string", "value": "trade_licence_renewal"}]}
out = ag.handler(ev, None)
body = json.loads(out["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
check("B lambda response shape + fee", out["response"]["function"] == "get_service_fee" and body["fee_ncd"] == 1200)
ev2 = dict(ev, function="submit_application", parameters=[{"name": "service", "type": "string", "value": "residency_renewal"},
                                                           {"name": "applicant_name", "type": "string", "value": "Test User"}])
b2 = json.loads(ag.handler(ev2, None)["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
check("B lambda submit returns reference", b2["submitted"] and b2["reference"].startswith("APP-2"))

# 5) usage logger + report with a temp log
tmp = Path(tempfile.mkdtemp()) / "usage.jsonl"
os.environ["USAGE_LOG"] = str(tmp)
os.environ["PRICE_TEST_MODEL_IN"], os.environ["PRICE_TEST_MODEL_OUT"] = "1", "2"
sys.path.insert(0, str(ROOT))
import common.usage as usage  # noqa: E402
usage.LOG = tmp
r = usage.log_call(source="smoke", model="test-model", input_tokens=1_000_000, output_tokens=500_000, latency_ms=10)
check("usage cost math", r["cost_usd"] == 2.0, r["cost_usd"])
usage.log_call(source="smoke", model="test-model", input_tokens=10, output_tokens=5, latency_ms=30)
rows = usage.report(tmp)
check("usage report aggregates", len(rows) == 2 and "| 2 |" in rows[1], rows[1])

# 6) promotion gate logic
gate = load(ROOT / "E_llmops_governance/promote_gate.py")
prod = {"accuracy": 0.75, "cost_per_case_usd": 0.0001, "failures": []}
check("gate promotes better+affordable", gate.decide({"accuracy": 0.92, "cost_per_case_usd": 0.00014, "failures": []}, prod)[0])
check("gate rejects accuracy drop", not gate.decide({"accuracy": 0.6, "cost_per_case_usd": 0.0001, "failures": []}, prod)[0])
check("gate rejects cost blow-up", not gate.decide({"accuracy": 0.95, "cost_per_case_usd": 0.001, "failures": []}, prod)[0])
check("gate rejects parse errors", not gate.decide({"accuracy": 0.9, "cost_per_case_usd": 0.0001,
                                                    "failures": [{"got": "PARSE_ERROR"}]}, prod)[0])
src = (ROOT / "E_llmops_governance/prompt_ab.py").read_text()
check("prompt_ab tags prompt_version", "prompt_version=version" in src)
cases = json.loads((ROOT / "E_llmops_governance/cases.json").read_text())
check("cases.json 12 labelled cases", len(cases) == 12 and all(c["intent"] in
      {"driving", "residency", "trade", "complaint", "other"} for c in cases))

# 7) banned-term scan (repo rule)
term = "cla" + "ude"
hits = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".venv" not in p.parts and "__pycache__" not in p.parts
        and (term in p.name.lower() or term in p.read_text(errors="ignore").lower())]
check("banned-term scan", not hits, ", ".join(hits))

print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
