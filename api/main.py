from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

load_dotenv()

from .schemas import (
    AnalyzeRequest,
    BranchRequest,
    FileUpdate,
    CommitRequest,
    PRRequest
)

from . import git_repository as repo

from agent.graph import agent
from .pr_integration import router as pr_integration_router

app = FastAPI(
    title="UC-05 AI Impact Analysis Assistant"
)
app.include_router(pr_integration_router)


@app.on_event("startup")
def startup():

    repo.ensure_repo()


# ------------------------------------------------------------------
# HEALTH
# ------------------------------------------------------------------

@app.get("/health")
def health():

    return {
        "status": "ok"
    }


# ------------------------------------------------------------------
# REPOSITORY
# ------------------------------------------------------------------

@app.get("/repository")
def repository():

    return {
        "name": "usecase5-demo/customer-platform",
        "branches": repo.branches(),
        "files": repo.files()
    }


@app.get("/repository/file")
def get_file(path: str):

    try:

        return {
            "path": path,
            "content": repo.read(path)
        }

    except Exception as ex:

        raise HTTPException(
            status_code=400,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# BRANCH
# ------------------------------------------------------------------

@app.post("/repository/branches")
def create_branch(req: BranchRequest):

    try:

        branch = repo.create_branch(
            req.branch_name
        )

        return {
            "branch": branch
        }

    except Exception as ex:

        raise HTTPException(
            status_code=400,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# UPDATE FILE
# ------------------------------------------------------------------

@app.put("/repository/file")
def update_file(req: FileUpdate):

    try:

        repo.write(
            req.path,
            req.content
        )

        return {
            "updated": True,
            "path": req.path
        }

    except Exception as ex:

        raise HTTPException(
            status_code=400,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# COMMIT
# ------------------------------------------------------------------

@app.post("/repository/commits")
def commit(req: CommitRequest):

    try:

        sha = repo.commit(
            req.message
        )

        return {
            "commit_sha": sha
        }

    except Exception as ex:

        raise HTTPException(
            status_code=400,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# CREATE PR
# ------------------------------------------------------------------

@app.post("/pull-requests")
def create_pr(req: PRRequest):

    try:

        return repo.create_pr(
            title=req.title,
            description=req.description,
            source_branch=req.source_branch,
            target_branch=req.target_branch
        )

    except Exception as ex:

        raise HTTPException(
            status_code=400,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# GET PR
# ------------------------------------------------------------------

@app.get("/pull-requests/{number}")
def get_pr(number: int):

    try:

        return repo.get_pr(number)

    except Exception as ex:

        raise HTTPException(
            status_code=404,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# ANALYZE PR
# ------------------------------------------------------------------

@app.post("/pull-requests/{number}/analyze")
def analyze_pr(number: int):

    try:

        pr = repo.get_pr(number)

        result = agent.invoke(
            {
                "event_id": f"pr-{number}",
                "event_type": "pull_request",
                "repository": "usecase5-demo/customer-platform",
                "pr_number": number,
                "commit_sha": pr["commit_sha"],
                "changed_files": pr["changed_files"]
            }
        )

        return result

    except Exception as ex:

        raise HTTPException(
            status_code=500,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# MERGE PR
# ------------------------------------------------------------------

@app.post("/pull-requests/{number}/merge")
def merge_pr(number: int):

    try:

        pr = repo.get_pr(number)

        analysis = agent.invoke(
            {
                "event_id": f"pr-{number}",
                "event_type": "pull_request",
                "repository": "usecase5-demo/customer-platform",
                "pr_number": number,
                "commit_sha": pr["commit_sha"],
                "changed_files": pr["changed_files"]
            }
        )

        if analysis["gate_status"] == "pending_approval":

            raise HTTPException(
                status_code=409,
                detail="Critical PR requires approval before merge."
            )

        merge_result = repo.merge_pr(number)

        return {
            "merged": True,
            "commit_sha": merge_result["commit_sha"]
        }

    except HTTPException:
        raise

    except Exception as ex:

        raise HTTPException(
            status_code=500,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# DIRECT ANALYZE API
# ------------------------------------------------------------------

@app.post("/analyze")
def analyze(req: AnalyzeRequest):

    try:

        return agent.invoke(
            req.model_dump()
        )

    except Exception as ex:

        raise HTTPException(
            status_code=500,
            detail=str(ex)
        )


# ------------------------------------------------------------------
# MERGE WEBHOOK
# ------------------------------------------------------------------

@app.post("/webhooks/merge")
def merge_webhook(req: AnalyzeRequest):

    try:

        data = req.model_dump()

        data["event_type"] = "merge"

        return agent.invoke(data)

    except Exception as ex:

        raise HTTPException(
            status_code=500,
            detail=str(ex)
        )