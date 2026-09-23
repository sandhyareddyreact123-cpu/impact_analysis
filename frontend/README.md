# UC-05 Executive Dashboard

A React/Vite dashboard that calls the existing FastAPI impact-analysis agent.

## Copy into the solution

Place the extracted `frontend` folder beside `agent`, `api`, and `tests`:

```text
uc05-impact-analysis-agent/
├── agent/
├── api/
├── tests/
└── frontend/
```

You may rename the extracted `uc05-executive-dashboard` folder to `frontend`.

## Run the backend

From the agent root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --reload --port 8000
```

Verify the backend at `http://127.0.0.1:8000/docs`.

## Run the frontend

Open another PowerShell terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Why no CORS change is required

`vite.config.js` proxies `/api/*` requests to `http://127.0.0.1:8000` and removes the `/api` prefix. The browser calls the Vite origin, and Vite forwards the request to FastAPI.

## Dashboard actions

- **Run impact analysis** calls `POST /analyze`.
- **Agent status** calls `GET /health`.
- **Simulate merge and refresh** calls `POST /webhooks/merge`.
- Low, High, and Critical scenarios use the same payloads as the POC fixtures.
