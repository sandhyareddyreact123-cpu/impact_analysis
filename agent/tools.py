from . import mocks
def load_dependency_graph():return mocks.graph()
def load_service_catalog():return mocks.catalog()
def load_test_mappings():return mocks.tests()
def post_pr_comment(body):return mocks.post_comment(body)
def send_notification(c,m):return mocks.notify(c,m)
def set_ci_gate(r,reason):return mocks.gate(r,reason)
def update_dependency_graph(p):return mocks.update(p)

def resolve_service(path, catalog=None):
    """Resolve a provider file path to the longest matching catalog service."""
    normalized = str(path or "").replace("\\", "/").strip("/").lower()
    names = [(str(item.get("name", "")).lower(), item.get("name"))
             for item in (catalog or load_service_catalog()).get("services", [])
             if isinstance(item, dict) and item.get("name")]
    matches = [item for item in names if normalized == item[0] or normalized.startswith(f"{item[0]}/")]
    return max(matches, key=lambda item: len(item[0]))[1] if matches else ""



# ============================================================================
# TEAM 3 - Dependency Graph & Consumer Analysis (FR-03, FR-04, FR-09 support)
# ----------------------------------------------------------------------------
# TEMPORARY NAMES (confirm, then change HERE only - never hardcode elsewhere):
#   Input  : changed_components[].service / .breaking   <- Team 2
#            changed_files[].service / .breaking        <- current POC shape
#   Output : dependency_paths, graph_coverage, warnings <- proposed to Team 1
#   Values : "unknown", "standard", "core_financial", internal/external/sdk
#
# EDGE DIRECTION: {"from": A, "to": B} means "A depends on B".
# Impact travels along REVERSED edges: changing B impacts A.
# ============================================================================

T3_MAX_DEPTH           = 6
T3_UNKNOWN_OWNER       = "unknown"
T3_DEFAULT_CRITICALITY = "standard"
T3_CORE_CRITICALITY    = "core_financial"
T3_CONSUMER_TYPES      = ("internal","external","sdk")

def _t3_warn(code,detail,**extra):return {"code":code,"detail":detail,"source":"team3",**extra}
def _t3_edge_ok(e):return isinstance(e,dict) and isinstance(e.get("from"),str) and isinstance(e.get("to"),str) and e["from"] and e["to"]
def _t3_cons_ok(c):return isinstance(c,dict) and isinstance(c.get("consumer"),str) and isinstance(c.get("provider"),str) and isinstance(c.get("type"),str)

def load_graph_indexed():
    """FR-03 foundation: load, validate, index. FAIL-OPEN - never raises."""
    g={"version":"unknown","edges":[],"reverse_index":{},"api_consumers":[],
       "schema_lineage":[],"catalog":{},"warnings":[],"degraded":False}
    try:
        for svc in (load_service_catalog() or {}).get("services",[]):
            if isinstance(svc,dict) and isinstance(svc.get("name"),str):g["catalog"][svc["name"]]=svc
    except Exception as exc:
        g["degraded"]=True;g["warnings"].append(_t3_warn("catalog_load_failed",f"service_catalog.json: {exc}"))
    try:
        raw=load_dependency_graph() or {}
        g["version"]=str(raw.get("version","unknown"))
        raw_edges=raw.get("edges",[]) or []
        g["edges"]=[e for e in raw_edges if _t3_edge_ok(e)]
        g["api_consumers"]=[c for c in (raw.get("api_consumers",[]) or []) if _t3_cons_ok(c)]
        g["schema_lineage"]=list(raw.get("schema_lineage",[]) or [])
        dropped=len(raw_edges)-len(g["edges"])
        if dropped:g["warnings"].append(_t3_warn("malformed_edge",f"{dropped} malformed edge(s) dropped"))
    except Exception as exc:
        g["degraded"]=True;g["warnings"].append(_t3_warn("graph_load_failed",f"dependency_graph.json: {exc}"));return g
    for e in g["edges"]:g["reverse_index"].setdefault(e["to"],[]).append(e["from"])
    for k in g["reverse_index"]:g["reverse_index"][k]=sorted(set(g["reverse_index"][k]))
    for node in sorted(graph_nodes(g)-set(g["catalog"])):
        g["warnings"].append(_t3_warn("unknown_node",f"'{node}' is in the dependency graph but not in the service catalog",service=node))
    return g

def graph_nodes(g):
    n=set()
    for e in g["edges"]:n.add(e["from"]);n.add(e["to"])
    for c in g["api_consumers"]:n.add(c["provider"])
    return n

def owner_of(g,service):
    """Null-safe: a catalog entry with an explicit null owner must not leak None."""
    return (g["catalog"].get(service,{}) or {}).get("owner") or T3_UNKNOWN_OWNER

def criticality_of(g,service):
    return (g["catalog"].get(service,{}) or {}).get("criticality") or T3_DEFAULT_CRITICALITY

def dependents_of(g,service):
    """Services that DEPEND ON `service` - the ones impacted when it changes."""
    return g["reverse_index"].get(service,[])

def graph_coverage(g):
    """Success criterion: dependency graph covers all catalog services."""
    catalog=set(g["catalog"]);nodes=graph_nodes(g)
    covered=sorted(catalog&nodes);missing=sorted(catalog-nodes)
    res={"graph_version":g["version"],"catalog_services":len(catalog),"services_in_graph":len(covered),
         "coverage_pct":round(100.0*len(covered)/len(catalog),2) if catalog else 0.0,
         "missing_from_graph":missing,"unknown_in_graph":sorted(nodes-catalog),
         "complete":bool(catalog) and not missing}
    if missing:
        g["warnings"].append(_t3_warn("coverage_gap",f"{len(missing)} catalog service(s) have no dependency-graph node",services=missing))
    return res

def changed_services(s):
    """Seed set. Reads BOTH shapes until Team 2 confirms which one ships."""
    out=set()
    for key in ("changed_components","changed_files"):
        for i in s.get(key) or []:
            if isinstance(i,dict) and isinstance(i.get("service"),str) and i["service"]:out.add(i["service"])
    return out

def breaking_services(s):
    out=set()
    for key in ("changed_components","changed_files"):
        for i in s.get(key) or []:
            if isinstance(i,dict) and i.get("breaking") and i.get("service"):out.add(i["service"])
    return out

def traverse_dependencies(g,changed,max_depth=T3_MAX_DEPTH):
    """FR-03 reverse-BFS. Shortest path wins; cycles guarded; depth bounded."""
    changed={s for s in changed if s};warnings=[]
    if not changed:
        warnings.append(_t3_warn("no_changed_service","No changed service could be resolved from the PR payload"))
        return {"services":[],"paths":[],"warnings":warnings}
    best={};visited=set(changed);truncated=set()
    queue=[(s,0,[s],s) for s in sorted(changed)];head=0
    while head<len(queue):
        node,depth,path,origin=queue[head];head+=1
        if depth>=max_depth:
            if dependents_of(g,node):truncated.add(node)
            continue
        for dep in dependents_of(g,node):
            if dep in changed or dep in path or dep in visited:continue
            visited.add(dep);np=path+[dep]
            best[dep]={"depth":depth+1,"path":np,"origin":origin}
            queue.append((dep,depth+1,np,origin))
    services=[];paths=[]
    for name in sorted(best):
        i=best[name];chain=" -> ".join(reversed(i["path"]))
        services.append({"name":name,"owner":owner_of(g,name),"criticality":criticality_of(g,name),
                         "depth":i["depth"],"origin":i["origin"],"path":i["path"],
                         "evidence":[f"dependency_path: {chain}",f"graph_version: {g['version']}"]})
        paths.append({"service":name,"origin":i["origin"],"depth":i["depth"],"hops":i["path"],"chain":chain})
    if truncated:
        warnings.append(_t3_warn("depth_truncated",f"Traversal stopped at max_depth={max_depth}; deeper impact not reported",services=sorted(truncated)))
    return {"services":services,"paths":paths,"warnings":warnings}

def map_api_consumers(g,changed,breaking=None):
    """FR-04: internal services, external integrations and SDK consumers."""
    changed={s for s in changed if s};breaking={s for s in (breaking or []) if s}
    warnings=[];hits=[]
    for rec in g["api_consumers"]:
        provider=rec["provider"]
        if provider not in changed:continue
        ctype=rec["type"] if rec["type"] in T3_CONSUMER_TYPES else "internal"
        if rec["type"] not in T3_CONSUMER_TYPES:
            warnings.append(_t3_warn("unknown_consumer_type",f"consumer '{rec['consumer']}' has type '{rec['type']}'; treated as internal"))
        owner=owner_of(g,rec["consumer"]) if ctype=="internal" else (rec.get("contact") or T3_UNKNOWN_OWNER)
        hits.append({"consumer":rec["consumer"],"provider":provider,"type":ctype,
                     "api":rec.get("api","unspecified"),"version":rec.get("version"),"owner":owner,
                     "breaking":provider in breaking,
                     "evidence":f"{rec['consumer']} consumes {provider} via {rec.get('api','unspecified')}"})
    hits.sort(key=lambda x:(x["type"],x["consumer"]))
    by_type={t:[h for h in hits if h["type"]==t] for t in T3_CONSUMER_TYPES}
    return {"consumers":hits,"by_type":by_type,"counts":{t:len(by_type[t]) for t in T3_CONSUMER_TYPES},
            "breaking_count":sum(1 for h in hits if h["breaking"]),
            "has_external_breaking":any(h["breaking"] and h["type"] in ("external","sdk") for h in hits),
            "warnings":warnings}

def resolve_owning_contacts(services,consumers=None):
    """FR-09 support: dedupe contacts, never emit the 'unknown' sentinel."""
    consumers=consumers or [];contacts=set();core=set();unresolved=[];owner_map={};warnings=[]

    def record(entity, owner, kind, critical=False):
        if not owner or owner == T3_UNKNOWN_OWNER:
            unresolved.append({"entity": entity, "kind": kind})
            return
        contacts.add(owner)
        if critical:
            core.add(owner)
        bucket = owner_map.setdefault(owner, [])
        if entity not in bucket:
            bucket.append(entity)
    
    for s in services:record(s.get("name",""),s.get("owner"),"service",critical=s.get("criticality")==T3_CORE_CRITICALITY)
    for c in consumers:record(c.get("consumer",""),c.get("owner"),f"consumer:{c.get('type','internal')}")
    if unresolved:
        warnings.append(_t3_warn("unresolved_owner",f"{len(unresolved)} impacted entit(ies) have no owner in the service catalog",entities=[u["entity"] for u in unresolved]))
    return {"contacts":sorted(contacts),"core_financial_contacts":sorted(core),"unresolved":unresolved,
            "owner_map":{k:sorted(v) for k,v in sorted(owner_map.items())},"warnings":warnings}