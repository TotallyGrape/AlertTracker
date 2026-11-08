# Spacetime integration

## Running architecture

Public feeds → independent Python/FastAPI collector → private HTTPS ingestion → Maincloud tables → direct React subscriptions.

Database: `texas-response-zl8x2` on `https://maincloud.spacetimedb.com`.
Dashboard: https://spacetimedb.com/texas-response-zl8x2
Module: `spacetimedb/src/index.ts`. Generated client bindings: `src/module_bindings/`.

The configured name did not exist under the logged-in account; setup created a new database with that name. Publishing used `--delete-data=never`. Existing module environment declarations were preserved.

## Start locally

Run two independent processes from the project root:

```powershell
# Terminal 1: collector and standalone read API
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: React
npm run dev -- --host localhost --port 5173
```

Maincloud is hosted; a local `spacetime start` is unnecessary for this configuration. Collector HTTP documentation remains at http://127.0.0.1:8000/docs. `/health` includes `spacetime_sync` with enabled/status/last_success/error. Public-source errors and synchronization errors are separate. Data already in Maincloud remains readable if the collector stops, and frontend heartbeats mark it stale.

`.env.local` now enables Spacetime and configures its public WebSocket host/name. `backend/.env` holds the ingestion URL and a generated private secret. Both files are ignored. A teammate can run the frontend with the public configuration but needs a securely provisioned collector secret to run ingestion. Do not commit secrets or place them in a `VITE_` variable. The frontend never receives the secret or CLI owner token.

## Tables and writes

| Table/view | Access | Purpose |
| --- | --- | --- |
| `incident` | Public reads; credential-checked handler writes | Feed records, coordinates, geometry JSON, details JSON, source, kind, category, active flag |
| `source_health` | Public reads; credential-checked handler writes | Source status, acquisition time, stale state, error and collector heartbeat |
| `resident_report` | Private | Owner identity, assistance request, location, status and creation time |
| `my_reports` | Per-caller read view | Only the authenticated connection identity's own reports |

`submit_report` validates required text and regional coordinates, assigns ownership from `ctx.sender`, limits an identity to ten open requests, and requires 30 seconds between submissions. `withdraw_report` checks ownership. There is no public reducer that writes official feeds. Role tabs are UI navigation, not authorization or responder credentials.

Resident submissions are not broadcast as public map pins or sent to emergency services. They persist for the current browser's stored identity; clearing browser storage loses access unless that token is recovered. This is an anonymous-identity hackathon foundation, not a completed user-account or coordinator-review system. No contact details are requested. Coordinator access, verification, assignment permissions and account recovery still need implementation before real operational use.

## Ingestion protocol

`POST https://maincloud.spacetimedb.com/v1/database/texas-response-zl8x2/route/ingest`

Required header: `x-ingest-secret`, matched against the private module environment value `INGEST_SECRET`. Spacetime does not automatically authenticate custom HTTP routes; the handler explicitly validates this credential. Missing/wrong credentials return 401. Invalid snapshots return 400. Bodies larger than 12 million characters return 413. The collector gets no database-owner credential.

Body:

```json
{
  "source": "nws_alerts",
  "health": {
    "status": "ok", "stale": false,
    "last_success": "2026-11-07T23:00:00+00:00",
    "interval_seconds": 60, "error": null
  },
  "records": []
}
```

`records` contains the normalized source's `items` described in `backend/README.md`, including located and unlocated records. An empty array means a **successful empty snapshot**, which deactivates previous records for that source. Omit `records` for health-only updates, including failures; this preserves the prior snapshot. Each supplied source snapshot is applied atomically. Source allowlist, stable ID namespace, duplicate IDs, required fields and coordinate ranges are checked before writing. Geometry/details JSON are opaque provider metadata stored as strings; network calls and normalization remain in Python.

The bridge runs every 30 seconds, sends records only for changed snapshot versions, and sends source-health heartbeats at least every 60 seconds while healthy. Up to three uploads run concurrently; a failed source does not prevent the others from completing. Only acknowledged uploads are remembered, so failures retry. Replaying a snapshot is safe: stable IDs upsert, and unchanged record contents avoid redundant row updates. Successful disappearance sets `active=false`; records are retained for history. History cleanup is not yet implemented.

To rotate the secret: generate a new random value, set the module's `INGEST_SECRET` using an environment-only publish, update `backend/.env`'s `SPACETIME_INGEST_SECRET`, then restart the collector. Never output either value to logs. Module publishing preserves unspecified private environment values. Do not use `--replace-env` unless intentionally replacing every configured secret.

## Frontend

`LiveMap` subscribes to active incidents and source health. `ResidentReports` subscribes to `my_reports`; submit/withdraw actions call generated reducers. React receives changes through Spacetime rather than polling FastAPI. The collector's standalone endpoints remain usable by other tools.

The map preserves the official Dallas boundary and unrestricted navigation. By default it shows incidents/warnings; facilities and observation/forecast layers are opt-in to reduce clutter. Red means an incident/warning, blue means observation/forecast, green means unverified facility and gray means stale data. Colors are not an AI severity ranking. Polygons use provider geometry; pins use provider coordinates or representative points. Unlocated calls are counted, not invented as pins. Popups render provider text with textContent, not raw HTML.

Source freshness considers last acquisition, configured interval, bridge heartbeat and connection state. Expired alerts/forecasts and old water/storm/earthquake records are hidden locally every 30 seconds even during collector outages. Facilities do not assert current availability. An empty map does not establish safety.

## Verification and remaining scope

Verified November 7, 2026:

- Module build, generated bindings and frontend production build.
- Eight Python tests, including retry acknowledgment, failure preservation and independent source uploads.
- Two datastore-harness tests covering report ownership, private views, validation and rate limits.
- Live Maincloud test with two anonymous identities: feed subscriptions, 12 source rows, report creation/withdrawal, other-owner rejection, and private-table subscription denial. The test request was withdrawn and never publicly mapped.
- All original adapters previously passed the live smoke test; current provider readiness remains available through source status.

Commands:

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
cd ../spacetimedb
npm test
# Optional real Maincloud verification (creates then withdraws a private test request)
$env:VERIFY_LIVE='true'
npx vitest run src/live.test.ts
Remove-Item Env:VERIFY_LIVE
```

Nemotron analysis, coordinator roles/review, responder availability/assignments, notifications, production sign-in and AI-job tables are not implemented in this setup. Those can build on the shared incident/request foundation. The Python service remains a separate process and must stay running for feed updates. No additional external API signup was required.
