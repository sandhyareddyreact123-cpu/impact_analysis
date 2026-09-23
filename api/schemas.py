from pydantic import BaseModel,Field
from typing import Any
class AnalyzeRequest(BaseModel):
 event_id:str;event_type:str="pull_request";repository:str;pr_number:int;commit_sha:str;changed_files:list[dict[str,Any]]=Field(default_factory=list)
class BranchRequest(BaseModel):branch_name:str
class FileUpdate(BaseModel):path:str;content:str
class CommitRequest(BaseModel):message:str
class PRRequest(BaseModel):title:str;description:str="";source_branch:str;target_branch:str="main"
