# WetlabDB

Tkinter-based wet-lab compound database with a hosted web UI. 
Developed to keep an overview of compounds in our lab.

Architecture and security hardening follow [`sar_alignment_handoff_v1/wetlabdb-local-llm-instructions.md`](sar_alignment_handoff_v1/wetlabdb-local-llm-instructions.md). Design notes: [`docs/p1-audit-and-recovery-design.md`](docs/p1-audit-and-recovery-design.md), [`docs/p1-authorization-grants-design.md`](docs/p1-authorization-grants-design.md), [`docs/p2-local-json-mode.md`](docs/p2-local-json-mode.md), [`docs/p2-storage-indexes.md`](docs/p2-storage-indexes.md).

## Web UI (primary)

Shared LAN deployment (Mongo in Docker):

```bash
export WETLABDB_ADMIN_PASSWORD=choose-a-password
export WETLABDB_SESSION_SECRET=choose-a-long-secret
docker compose up --build
```

Open `http://<lab-host>:8000`. Firewall that port; Mongo is not published to the host.

Set secrets via a `.env` file (see [`.env.example`](.env.example)): Compose requires `WETLABDB_SESSION_SECRET` (≥32 characters) and `WETLABDB_ADMIN_PASSWORD`. In remote mode the app refuses known defaults unless `WETLABDB_ALLOW_INSECURE_DEV=1`.

When terminating TLS at a reverse proxy, set `WETLABDB_SESSION_HTTPS_ONLY=1` and ensure the proxy forwards `X-Forwarded-Proto: https` so session cookies are marked `Secure`.

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

**Operations:** liveness `GET /api/health/live`, readiness `GET /api/health/ready`, admin metrics `GET /api/metrics` (JSON) and `GET /api/metrics/prometheus` (Prometheus text, including latency histogram buckets and storage-error counters). Compound lists support optional `?limit=` (max 500), `?cursor=`, and `?fields=` (comma-separated projection). Text filters use MongoDB query pushdown in remote mode. Admins get an **Admin** nav page (audit log + trash restore). Operational bounds: `GET /api/limits` and [`docs/p2-handoff-checklist.md`](docs/p2-handoff-checklist.md). Search/chem: [`docs/p2-search-chem-limits.md`](docs/p2-search-chem-limits.md). Mongo indexes: [`docs/p2-storage-indexes.md`](docs/p2-storage-indexes.md). CI: [`docs/ci-lockfiles.md`](docs/ci-lockfiles.md).

Legacy desktop UI: `python -m wetlabdb --tk`.