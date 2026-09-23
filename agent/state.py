from typing import TypedDict,Any
class ImpactState(TypedDict,total=False):
 event_id:str;event_type:str;repository:str;pr_number:int;commit_sha:str;changed_files:list[dict[str,Any]];changed_components:list[dict[str,Any]];affected_services:list[dict[str,Any]];api_consumers:list[dict[str,Any]];schema_impacts:list[dict[str,Any]];affected_tests:list[dict[str,Any]];owning_contacts:list[str];severity:str;severity_reasons:list[str];notification_status:str;gate_status:str;comment_markdown:str;graph_updated:bool;graph_version:str;started_at:float;elapsed_seconds:float


 # ---- TEAM 3 additions (FR-03 / FR-04 / FR-09 support) ----
 dependency_paths:list[dict[str,Any]];graph_coverage:dict[str,Any];owner_map:dict[str,list[str]];unresolved_owners:list[dict[str,Any]];consumer_counts:dict[str,int];consumers_by_type:dict[str,list[dict[str,Any]]];has_external_breaking:bool;graph_degraded:bool;warnings:list[dict[str,Any]]