import re,time
from .tools import *
from . import llm as _llm
from . import pr_comment as _pr
from .prompts import SYSTEM_PROMPT, build_payload, build_user_prompt
def init(s):d=dict(s);d["started_at"]=time.perf_counter();return d
def diff(s):
 out=[]
 for f in s.get("changed_files",[]):
  text=(f.get("path","")+" "+f.get("patch","")).lower();k=[]
  if re.search(r'controller|/api/|endpoint',text):k.append("api_endpoint")
  if re.search(r'model|dto|entity',text):k.append("data_model")
  if re.search(r'schema|migration|\.sql',text):k.append("schema")
  if not k:k=["source_file"]
  out += [{"path":f["path"],"kind":x,"symbol":f.get("symbol",f["path"].split('/')[-1]),"evidence":f["path"]} for x in k]
 return {**s,"changed_components":out}


# ---- TEAM 3 (FR-03) --------------------------------------------------------
def dependencies(s):
 g=load_graph_indexed();r=traverse_dependencies(g,changed_services(s));cov=graph_coverage(g);own=resolve_owning_contacts(r["services"])
 return {**s,"affected_services":r["services"],"dependency_paths":r["paths"],"owning_contacts":own["contacts"],
         "graph_version":g["version"],"graph_coverage":cov,"graph_degraded":g["degraded"],
         "owner_map":own["owner_map"],"unresolved_owners":own["unresolved"],
         "warnings":list(s.get("warnings") or [])+g["warnings"]+r["warnings"]+own["warnings"]}
# ---- TEAM 3 (FR-04) --------------------------------------------------------
def consumers(s):
 g=load_graph_indexed();m=map_api_consumers(g,changed_services(s),breaking_services(s))
 own=resolve_owning_contacts(s.get("affected_services") or [],m["consumers"])
 return {**s,"api_consumers":m["consumers"],"owning_contacts":own["contacts"],"consumer_counts":m["counts"],
         "consumers_by_type":m["by_type"],"has_external_breaking":m["has_external_breaking"],
         "owner_map":own["owner_map"],
         "warnings":list(s.get("warnings") or [])+m["warnings"]+own["warnings"]}

#--end for Team 3

def schemas(s):
 line=load_dependency_graph()["schema_lineage"];changed={x.get("schema") for x in s.get("changed_files",[]) if x.get("schema")};breaking={x.get("schema") for x in s.get("changed_files",[]) if x.get("breaking")};out=[]
 for n in changed:
  u=[x for x in line if x["schema"]==n];out.append({"schema":n,"breaking":n in breaking,"readers":[x["service"] for x in u if x["mode"]=="read"],"writers":[x["service"] for x in u if x["mode"]=="write"],"pipelines":[x["service"] for x in u if x["type"]=="pipeline"]})
 return {**s,"schema_impacts":out}
def testmap(s):
 keys={x["symbol"] for x in s.get("changed_components",[])}|{x.get("service") for x in s.get("changed_files",[])};out=[]
 for m in load_test_mappings()["mappings"]:
  if m["component"] in keys:out+=m["tests"]
 return {**s,"affected_tests":list({x["name"]:x for x in out}.values())}


def severity(s):
 sv=s.get("affected_services",[]);c=s.get("api_consumers",[]);sc=s.get("schema_impacts",[]);core=any(x.get("criticality")=="core_financial" for x in sv);ba=any(x.get("breaking") for x in c);bs=any(x.get("breaking") for x in sc);ext=any(x.get("type")=="external" for x in c)
 if core and (ba or bs):sev="Critical";r=["Breaking impact reaches a core financial service"]
 elif ba or bs or ext:sev="High";r=(["Breaking API contract change"] if ba else [])+(["Breaking shared schema change"] if bs else [])+(["External consumer affected"] if ext else [])
 elif sv or c or sc:sev="Medium";r=["Contained registered downstream impact"]
 else:sev="Low";r=["No registered downstream dependency found"]
 # rule_severity is preserved so the LLM can only ever escalate from this floor.
 return {**s,"severity":sev,"severity_reasons":r,"rule_severity":sev}

# ---- ACTIONS: single LLM call, then gate/notify/comment ---------------------
# ORDER IS LOAD-BEARING: LLM -> escalate-only -> gate -> notify -> comment.
# The gate and the notification must both see the FINAL severity, otherwise an
# escalated Critical PR would be merged with gate_status "not_required".
def actions(s):
 rule_sev=s.get("rule_severity") or s.get("severity","Low")
 payload=build_payload(s)
 result,status=_llm.analyze(payload,SYSTEM_PROMPT,build_user_prompt(payload))

 final_sev=rule_sev;reasons=list(s.get("severity_reasons") or [])
 reasoning="";risks=[];llm_comment=None
 if result:
  final_sev=_llm.escalate_only(rule_sev,result["severity"])
  for r in result["severity_reasons"]:
   if r not in reasons:reasons.append(r)
  reasoning=result["reasoning"];risks=result["additional_risks"]
  if _pr.looks_complete(result["comment_markdown"]):llm_comment=result["comment_markdown"]

 warnings=list(s.get("warnings") or [])
 if status.get("warning"):warnings.append(status["warning"])
 if result and not llm_comment:
  warnings.append({"code":"llm_comment_incomplete","detail":"LLM comment missing required FR-08 sections; deterministic comment used","source":"llm"})
 if result and _llm.SEVERITY_ORDER.index(result["severity"])<_llm.SEVERITY_ORDER.index(rule_sev):
  warnings.append({"code":"llm_downgrade_blocked","detail":f"LLM suggested {result['severity']}; rule floor {rule_sev} retained","source":"llm"})

 s2={**s,"severity":final_sev,"severity_reasons":reasons,"rule_severity":rule_sev,
     "severity_reasoning":reasoning,"llm_additional_risks":risks,
     "llm_status":{"state":status["state"],"reason":status["reason"],"model":status["model"],
                   "escalated":final_sev!=rule_sev},
     "warnings":warnings}

 gate=set_ci_gate(final_sev=="Critical","Critical impact requires approval")
 note=send_notification(s2.get("owning_contacts",[]),f"{final_sev} impact") if final_sev in ("High","Critical") else {"sent":False}
 s2["gate_status"]=gate["status"]
 s2["notification_status"]="sent" if note.get("sent") else "not_required"

 body=llm_comment or _pr.render_fallback(s2,gate["status"])
 s2["comment_markdown"]=body
 s2["comment_file"]=_pr.write_comment_file(s2,body)
 post_pr_comment(body)
 s2["elapsed_seconds"]=round(time.perf_counter()-s["started_at"],5)
 return s2

def merge(s):
 r=update_dependency_graph(s)
 return {**s,"graph_updated":r["updated"],"graph_version":r.get("graph_version",r["version"]),
     "graph_refresh":r,"graph_refresh_message":r.get("message", "Dependency graph refresh completed")}
