import json
from pathlib import Path
F=Path(__file__).resolve().parents[1]/"tests"/"fixtures"
def load(n):return json.loads((F/n).read_text())
def graph():return load("dependency_graph.json")
def catalog():return load("service_catalog.json")
def tests():return load("test_mappings.json")
def post_comment(body):return {"posted":True,"body":body}
def notify(contacts,message):return {"sent":bool(contacts),"contacts":contacts}
def gate(required,reason):return {"status":"pending_approval" if required else "not_required","reason":reason}
def update(payload):
	version = payload.get("commit_sha", "unknown")
	return {"updated": True, "version": version, "graph_version": version,
			"service_catalog_synced": True, "coverage_validated": True,
			"message": f"Dependency graph refreshed successfully at {version}"}
