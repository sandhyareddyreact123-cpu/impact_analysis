import json,time
from pathlib import Path
from agent.graph import agent
P=Path(__file__).parent/"fixtures"
def load(n): return json.loads((P/n).read_text())
def test_scenarios_and_thresholds():
 for f,e in [("low_pr.json","Low"),("high_api_break.json","High"),("critical_financial_schema.json","Critical")]:
  t=time.perf_counter(); r=agent.invoke(load(f)); assert r["severity"]==e; assert time.perf_counter()-t<180; assert all(k in r for k in ["comment_markdown","affected_services","affected_tests"])
 assert agent.invoke(load("critical_financial_schema.json"))["gate_status"]=="pending_approval"
def test_merge(): assert agent.invoke({"event_type":"merge","commit_sha":"m1"})["graph_updated"]
def test_api():
 from fastapi.testclient import TestClient
 from api.main import app
 c=TestClient(app); assert c.get("/health").json()["status"]=="ok"; assert c.post("/analyze",json=load("critical_financial_schema.json")).json()["severity"]=="Critical"
