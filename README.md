# UC-05 Git-Integrated End-to-End POC

This package contains:

- the LangGraph/FastAPI impact-analysis backend;
- a genuine local Git repository in `sample_repository`;
- API endpoints that browse files, create branches, update files, commit changes, create a PR record from `git diff`, and analyze that PR;
- a React dashboard that uses those Git endpoints.


The integration aligns with the PRD/build design in which the Git provider supplies PR metadata and diff data while the agent posts comments and gate results through adapter contracts.

## Local Git versus hosted Git

This package uses a **real local Git repository** through the installed `git` command. It does not create a hosted GitHub, GitLab, or Azure DevOps repository, because hosted integration requires your organization-specific URL, project/repository identifiers, and credentials. The adapter boundary is isolated in `api/git_repository.py` so it can later be replaced with a hosted-provider adapter.

## Run

### Backend

```powershell
cd C:\VanGuard\UC05\uc05-git-integrated-solution
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python setup_sample_repo.py
python -m uvicorn api.main:app --reload --port 8000
```

Verify the API in the browser at `http://127.0.0.1:8000/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Demo

1. Select a file from the actual local Git repository.
2. Modify its content.
3. Enter a feature branch and PR title.
4. Select **Commit change and create PR**. The backend creates/switches the branch, writes the file, creates a Git commit, calculates `git diff`, and creates a PR record.
5. Select **Run impact analysis**. The backend sends the Git-derived changed files into the LangGraph agent.
6. Review severity, affected services, tests, notifications, gate, and PR comment.

## Hosted-provider next step

Hosted pull-request ingestion is available at `POST /webhooks/{provider}/pull-request`.
The endpoint uses the REST adapters in `pr_integration/git_adapter.py` and does not use the local Git repository.

Configure these environment variables before starting the API:

```text
GITHUB_TOKEN=
GITHUB_WEBHOOK_SECRET=
AZURE_DEVOPS_TOKEN=
AZURE_DEVOPS_WEBHOOK_TOKEN=
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your-organization
AZURE_DEVOPS_PROJECT=
```

Use `github` or `azure_devops` as the provider path. GitHub requires the `X-Hub-Signature-256` and `X-GitHub-Event` headers. Azure DevOps requires the configured authorization token and event type header. The existing local Git endpoints remain available for the POC dashboard; hosted webhook processing is a separate path.
