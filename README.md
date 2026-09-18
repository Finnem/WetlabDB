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

Open `http://<lab-host>:8000`. Firewall that port; Mongo is not published to the host.

Serverless (JSON files, no Mongo):

```bash
docker compose -f docker-compose.serverless.yml up --build
```

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

Legacy desktop UI: `python -m wetlabdb --tk`.