# Texas Response

A multi-hazard disaster-assistance app for Greater Dallas / Dallas–Fort Worth, built for HackUTD.

It aims to turn scattered alerts into coordinated help. A resident's request should be acknowledged, assigned, followed up and resolved, with a shared record of progress. Public hazard feeds supply the context, NVIDIA Nemotron investigates emerging incidents, and SpacetimeDB keeps residents, coordinators and responders in sync.

> **Not a 911 replacement.** This is a hackathon prototype. In an emergency, call 911. Any simulated residents or teams in a demo are labeled as simulated and do not represent real agencies.

## Status

| Area | State |
| --- | --- |
| Resident, Coordinator and Responder tabs | Built: shared shell; resident requests supported, coordinator/responder workflows remain placeholders |
| Interactive DFW map | Built: MapLibre GL JS, OpenFreeMap basemap, Dallas city-limits outline |
| Spacetime connection | Maincloud subscriptions and secure Python ingestion configured |
| Backend module | Feed tables, source health, private resident requests and owner-checked reducers |
| Requests, assignments, responder availability | Resident submission/withdrawal built; assignments and availability not built |
| Hazard feed ingestion and map layers | Python collectors, cached feeds, map layers, source freshness and rule-based priority |
| Nemotron | Optional cached summaries and validated priority decisions; falls back to source text/rules |
| Geocoding | Cached Dallas GIS block/intersection matching for police calls; approximate locations labeled |
| Production sign-in, notifications, routing | Not built |

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | React 18, TypeScript, Vite |
| Map | MapLibre GL JS with OpenFreeMap tiles (no key) |
| Backend, database and live sync | SpacetimeDB 2.14 TypeScript module |
| External API calls | Separate Python FastAPI service with background collectors |
| AI | Optional Nemotron background worker inside FastAPI using an OpenAI-compatible remote endpoint |

FastAPI collects and enriches feeds centrally, then synchronizes them into Maincloud. React subscribes directly to Spacetime for live updates. Feed collection, geocoding, AI and synchronization run inside the same Python service; they do not require separate local workers.

## Quick start

Requires Node `^22.12.0` or `>=24.0.0`.

### Windows: launch the whole app

Double-click **`start-app.bat`**, or run it from any folder:

```bat
start-app.bat
```

This starts FastAPI on **http://127.0.0.1:8000** and Vite on **http://localhost:5173/** in the background. Open the frontend URL after startup. Logs are written to `.logs/backend.out.log`, `.logs/backend.err.log`, `.logs/frontend.out.log` and `.logs/frontend.err.log`. It checks dependencies, reuses services already running at those addresses, and does not install packages, overwrite configuration or restart existing processes. Run `start-app.bat -CheckOnly` to validate setup without launching anything.

First-time dependencies:

```powershell
npm install
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

FastAPI starts the feed collectors, cached police geocoder, Spacetime synchronization, and optional Nemotron worker internally. Maincloud is hosted, so no local Spacetime server is needed for the current configuration. The configured NVIDIA/NIM endpoint must be reachable for AI processing; the launcher does not provision a remote GPU or inference server. Settings remain in `.env.local` and `backend/.env`; see [SPACETIME_INTEGRATION.md](SPACETIME_INTEGRATION.md) and [backend/README.md](backend/README.md). Missing AI credentials leave the optional worker disabled.

To stop a background service, use Task Manager with the PID printed at startup. Stop both services before relaunching when you need backend changes loaded.

### Frontend only

```sh
npm install
npm run dev
```

Open the URL Vite prints (normally http://localhost:5173/). The frontend runs without a database. The basemap needs an internet connection.

```sh
npm run build
```

`npm run build` type-checks and builds the frontend into `dist/`.

## Connecting the backend

You need the [SpacetimeDB CLI](https://spacetimedb.com/install) for these steps.

1. Install module dependencies: `npm install --prefix spacetimedb`
2. Add tables, reducers and procedures in `spacetimedb/src/index.ts`.
3. Regenerate client bindings after every schema change: `npm run spacetime:generate`
4. Publish locally with `npm run spacetime:publish:local` (start a local server first with `spacetime start`), or to Maincloud with `npm run spacetime:publish`.
5. In `.env.local`, set `VITE_SPACETIMEDB_ENABLED=true` plus the host and database name, then restart Vite. See `.env.example`.

`VITE_` variables are visible in the browser. Put only public settings there.

## API keys

Keys live in the Spacetime database's private environment, never in code or the frontend.

- `spacetimedb/src/index.ts` declares each key under `env`. Procedures read them as `ctx.env.NVIDIA_API_KEY` and so on.
- Every key is optional. A procedure should mark its source "missing key" when its value is `undefined`.
- Copy `spacetimedb/.env.example` to `spacetimedb/.env` and fill in your keys. All `.env` files except `.env.example` are gitignored.
- Values are supplied when publishing. Run `spacetime publish --help` to find the flag for environment values in your CLI version.
- Never return keys to clients, pass them as reducer arguments, log them, or store them in table rows.
- Share keys through a password manager, not git or chat.

Sign-ups, from most open to least:

| Service | Needed for | Access |
| --- | --- | --- |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/) | Satellite heat detections | Free `MAP_KEY` |
| [USGS Water Data](https://api.waterdata.usgs.gov/signup) | Higher request limits (optional) | Free |
| [Socrata app token](https://dev.socrata.com/docs/app-tokens.html) | Dallas Open Data request pool (optional) | Free |
| [NVIDIA API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b-infer) | Nemotron | Account required |
| [AirNow](https://docs.airnowapi.org/webservices) | Air quality | Account required |
| [ERCOT Public API](https://developer.ercot.com/applications/pubapi/ERCOT%20Public%20API%20Registration%20and%20Authentication/) | Official grid data (optional) | Key plus login token |
| [DART](https://dart.developer.azure-api.net/) | Realtime transit | Portal sign-in and subscription |
| [DriveTexas](https://api.drivetexas.org/api-docs) | Road closures | Approval timeline unknown; request early |

## Data sources

Planned feeds, none integrated yet:

- **Weather and alerts:** NWS Alerts, NWS forecasts and observations, SPC outlooks, NEXRAD radar tiles
- **Water:** USGS gauges, NOAA NWPS river forecasts, TWDB reservoirs
- **Roads and transit:** DriveTexas, DART
- **Local incidents:** Dallas Police Active Calls, Dallas Fire-Rescue active calls (best-effort, undocumented file), Dallas 311, Iowa Environmental Mesonet storm reports
- **Outages:** ORNL ODIN, ERCOT grid status, IODA
- **Fire, smoke and air:** NASA FIRMS, NIFC WFIGS, NOAA HMS smoke, AirNow, US Drought Monitor
- **Other hazards and reference:** USGS earthquakes, FEMA shelters, OpenFEMA declarations, National Inventory of Dams, EPA facilities

`PROJECT_HANDOFF.txt` lists every source with its limitations. The team's API reference doc has endpoints, test results and traps for each feed.

## Data rules

These apply to every feature:

- Label each record as observed, reported, forecast or inferred, and show when it was updated.
- No data means unknown, not safe.
- A reported hazard doesn't prove someone needs help, and a disappearing call doesn't prove it was resolved.
- A base-to-scene driving estimate is never an emergency response ETA.
- Resident locations, contact details, medical and accessibility needs, and responder movement stay private. Expose them only through authorized views.
- A human coordinator approves consequential recommendations and assignments. Nemotron proposes; it doesn't dispatch.
- Text from external feeds is untrusted data, never instructions for the AI.

## Project layout

```text
src/
  App.tsx                    Shell and tab navigation
  main.tsx                   Entry point and optional Spacetime provider
  screens/                   Resident, Coordinator and Responder screens
  components/DallasMap.tsx   Shared MapLibre map and controls
  components/WorkspaceParts.tsx  Shared headings and empty states
  module_bindings/           Generated Spacetime client bindings (do not edit)
  styles.css                 Responsive styling
spacetimedb/
  src/index.ts               Backend module: schema, env declarations, future logic
  .env.example               Backend key names
public/data/
  dallas-city-limits.geojson Dallas city-limits snapshot (see its README)
PROJECT_HANDOFF.txt          Goals, scope, sources and build order
CLAUDE.md / AGENTS.md        SpacetimeDB rules for coding agents
```

## Attribution

Basemap © [OpenFreeMap](https://openfreemap.org/) and © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors. City limits from City of Dallas GIS Services. Keep provider attribution visible as new layers are added.

## License

[Apache License 2.0](LICENSE).

## Separate disaster-feed API

The Python FastAPI service lives in backend/. See [backend/README.md](backend/README.md) for setup, endpoints, source coverage and the future frontend connection contract. It runs on port 8000; the frontend remains independent on port 5173.


Spacetime integration is now configured: see [SPACETIME_INTEGRATION.md](SPACETIME_INTEGRATION.md) for Maincloud, ingestion, live map subscriptions, private resident requests and startup instructions.

