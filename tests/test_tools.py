from agent.tools import *
def test_contracts():
 assert load_dependency_graph()["edges"] and load_service_catalog()["services"] and load_test_mappings()["mappings"]
 assert post_pr_comment("x")["posted"] and set_ci_gate(True,"x")["status"]=="pending_approval"
