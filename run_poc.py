import argparse,json
from pathlib import Path
from agent.graph import agent
P=Path(__file__).parent; ap=argparse.ArgumentParser(); ap.add_argument("--fixture",default="tests/fixtures/critical_financial_schema.json"); a=ap.parse_args(); result=agent.invoke(json.loads((P/a.fixture).read_text())); out=P/"output"; out.mkdir(exist_ok=True); (out/"impact_result.json").write_text(json.dumps(result,indent=2)); (out/"pr_comment.md").write_text(result.get("comment_markdown","")); print(json.dumps({k:result.get(k) for k in ["severity","severity_reasons","gate_status","notification_status","elapsed_seconds"]},indent=2))
