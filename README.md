# WetlabDB

Tkinter-based wet-lab compound database with a hosted web UI. 
Developed to keep an overview of compounds in our lab.
## Web UI (primary)

Shared LAN deployment (Mongo in Docker):

```bash
export WETLABDB_ADMIN_PASSWORD=choose-a-password
export WETLABDB_SESSION_SECRET=choose-a-long-secret
docker compose up --build
```

Serverless (JSON files, no Mongo):

```bash
docker compose -f docker-compose.serverless.yml up --build
```

This runs **local JSON mode** (single-process; see [`docs/p2-local-json-mode.md`](docs/p2-local-json-mode.md)). It is not a multi-tenant hosted database.

Local development without Docker:

```bash
pip install -e '.[mongo,dev]'
python -m wetlabdb --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend && npm install && npm run dev
```

Vite proxies `/api` to port 8000. Bootstrap admin comes from `WETLABDB_ADMIN_USER` / `WETLABDB_ADMIN_PASSWORD` (defaults `admin` / empty unless set).

The browser UI sends `X-WetlabDB-Request: 1` on mutating API calls (CSRF mitigation). Custom API clients must do the same except for `POST /api/login`.

**Operations:** liveness `GET /api/health/live`, readiness `GET /api/health/ready`, admin metrics `GET /api/metrics` (JSON) and `GET /api/metrics/prometheus` (Prometheus text, including latency histogram buckets and storage-error counters). Compound lists support optional `?limit=` (max 500), `?cursor=`, and `?fields=` (comma-separated projection). Text filters use MongoDB query pushdown in remote mode. Admins get an **Admin** nav page (audit log + trash restore). Legacy desktop UI: `python -m wetlabdb --tk`.