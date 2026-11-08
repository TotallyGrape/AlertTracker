# Rally Point

**Where Dallas comes together.**

A multi-hazard disaster-assistance workspace for Greater Dallas / Dallas–Fort Worth, built for HackUTD. It turns scattered public alerts into a shared, live picture, and helps people review and prioritize resident assistance needs alongside current hazards.

> **Not a 911 replacement.** This is a hackathon prototype. In an emergency, call 911. Requests are unverified and are not dispatched to emergency services. Any simulated residents or teams in a demo are labeled as simulated and do not represent real agencies.

## What it does

| Area | State |
| --- | --- |
| Live hazard map | 15 external-source adapters plus an internal community-report adapter; layered pins and areas with source health and freshness |
| Priority 1–10 | Every alert and incident is scored by explainable rules; Nemotron can refine the score with guardrails |
| AI summaries | Optional Nemotron headlines and summaries for alerts, storm reports and police call codes |
| Police call locations | Street text geocoded with the City of Dallas locator; approximate locations are labeled |
| Resident requests | Structured, private requests with optional AI assessment, 24-hour expiry and withdrawal ([details](RESIDENT_REPORTING.md)) |
| Regional issues | Scrollable Nemotron responder cards with cited evidence, uncertainty, severity limits and filters |
| Community concerns | Anonymous approximate-area summaries from multiple resident identities contribute pins and shared AI concerns under a labeled hackathon assumption |
| Bounded AI investigations | Nemotron chooses up to two weather, river or traffic checks before final assessment; investigation traces remain in the API, hidden from cards |
| Two-page navigation | **01 Resident** for private requests and the map; **02 Responder** for shared issue cards above the map. Coordinator navigation has been removed |
| Assignment, resolution and dispatch | Not built; submitting a request does not guarantee assistance |
| Production sign-in, notifications, routing | Not built |

## How it fits together

```text
Public feeds ──► FastAPI collector (backend/) ──► private HTTPS ingest ──► SpacetimeDB on Maincloud ──► React app (live subscriptions)
                  • polls external feeds + community summaries           (secret header)          • incident, source_health,
                  • geocodes police calls                                              issue_card (public)
                  • rule priority + optional Nemotron                                  • resident_report (private,
                  • caches to backend/.cache                                             owner-only view)
```

- **FastAPI** fetches each feed once for everyone, enriches records (water risk, priority, geocoding, AI) and keeps a read-only REST API on port 8000.
- **SpacetimeDB** stores the shared state and pushes changes to every open browser. Raw resident requests stay in a private table; each person sees only their own through the `my_reports` view. A credential-protected route supplies anonymous coarse-area aggregates to the collector.
- **React** subscribes to Spacetime directly. Browsers never call the hazard APIs.

## Quick start

Requires Node `^22.12.0` or `>=24.0.0` and Python 3.11+.

First-time setup, from the repository root:

```powershell
npm install
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

Then get the two private config files from a teammate (they are gitignored): `.env.local` (public Spacetime host and database name) and `backend/.env` (ingest URL and secret, optional API keys). See [Configuration](#configuration).

### Windows: launch everything

Double-click **`start-app.bat`**, or run it from a terminal:

```bat
start-app.bat
```

It starts FastAPI on **http://127.0.0.1:8000** and Vite on **http://localhost:5173/** in the background, reuses services already running at those addresses, and writes logs to `.logs/`. It does not install packages, overwrite configuration or restart running processes. `start-app.bat -CheckOnly` validates setup without launching. To stop a service, end its PID (printed at startup) in Task Manager; stop both before relaunching to load backend changes.

### Manually

```powershell
# Terminal 1: feed collector, geocoder, Spacetime sync and optional AI
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: React
npm run dev
```

### Frontend only

`npm run dev` works without a database or collector when `VITE_SPACETIMEDB_ENABLED` is not `true`; you get the shell and basemap only. The basemap and fonts need an internet connection. `npm run build` type-checks and builds into `dist/`.

## Configuration

All `.env` files except `.env.example` are gitignored. Never put secrets in `VITE_` variables: the browser can read them.

| File | Holds | Example |
| --- | --- | --- |
| `.env.local` | Public frontend settings | `VITE_SPACETIMEDB_ENABLED`, `VITE_SPACETIMEDB_HOST`, `VITE_SPACETIMEDB_DB_NAME` (see `.env.example`) |
| `backend/.env` | Collector settings and private keys | `SPACETIME_INGEST_URL`, `SPACETIME_INGEST_SECRET`, `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `NEMOTRON_MODEL`, `TOMTOM_API_KEY`, `BBOX`, `ENABLED_SOURCES` (see `backend/.env.example`) |
| Spacetime module environment | Private database values set at publish time | `INGEST_SECRET` must match the collector's `SPACETIME_INGEST_SECRET`; other declared keys are listed in `spacetimedb/.env.example` |

**Nemotron:** put a hosted key from build.nvidia.com (starts with `nvapi-`) in `backend/.env` as `NVIDIA_API_KEY`, then restart the collector. A Brev key (`bak-…`) manages Brev machines and does not work with the hosted API; to self-host Nemotron on Brev, point `NVIDIA_BASE_URL` at that endpoint instead. With no working key the app runs on rule-based priority and original feed text. `/health` → `nemotron` shows the worker's status.

API sign-ups, from most open to least: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/) (free `MAP_KEY`), [USGS Water Data](https://api.waterdata.usgs.gov/signup) (optional, higher limits), [Socrata app token](https://dev.socrata.com/docs/app-tokens.html) (optional), [NVIDIA](https://build.nvidia.com/) (Nemotron), [TomTom](https://developer.tomtom.com/) (traffic incidents), [AirNow](https://docs.airnowapi.org/webservices), [ERCOT](https://developer.ercot.com/applications/pubapi/ERCOT%20Public%20API%20Registration%20and%20Authentication/) (optional), [DART](https://dart.developer.azure-api.net/), [DriveTexas](https://api.drivetexas.org/api-docs) (approval time unknown; request early). Share keys through a password manager, not git or chat.

## Data sources

The 15 external-source adapters below are configured alongside the internal community-report adapter. Check `/sources` for current health and freshness. Zero records can mean no matching published data; it does not establish that nothing is happening.

| Adapter | Source | Poll | Key |
| --- | --- | --- | --- |
| `nws_alerts` | [NWS active alerts](https://www.weather.gov/documentation/services-web-alerts), Texas, filtered to the region; zone shapes fill missing geometry | 60 s | No, User-Agent |
| `nws_weather` | [NWS](https://www.weather.gov/documentation/services-web-api) forecast for central Dallas | 15 min | No, User-Agent |
| `nwps` | [NOAA NWPS](https://api.water.noaa.gov/nwps/v1/docs/) river status and flood thresholds (Trinity at Dallas by default, `NWPS_GAUGES`) | 5 min | No |
| `usgs_water` | [USGS Water Data](https://api.waterdata.usgs.gov/docs/ogcapi/) latest gauge height and streamflow | 5 min | No |
| `dallas_police` | [Dallas Police active calls](https://www.dallasopendata.com/Public-Safety/Dallas-Police-Active-Calls/9fxf-t2tr/about_data), geocoded with the City of Dallas street locator | 2 min | No |
| `dallas_311` | [Dallas 311 service requests](https://www.dallasopendata.com/d/d7e7-envw), hazard-related types only (flooding, drainage, water mains, downed trees, signals) | 1 h | No |
| `iem` | [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/) preliminary NWS storm reports, Fort Worth office, last 24 h | 5 min | No |
| `tomtom` | [TomTom](https://developer.tomtom.com/) traffic incidents across DFW (two requests per cycle) | 15 min (`TOMTOM_POLL_SECONDS`, min 5 min) | `TOMTOM_API_KEY` |
| `nifc` | [NIFC WFIGS](https://data-nifc.opendata.arcgis.com/) current wildfire perimeters | 10 min | No |
| `earthquakes` | [USGS earthquakes](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php), past day | 60 s | No |
| `eonet` | [NASA EONET](https://eonet.gsfc.nasa.gov/) natural events | 30 min | No |
| `fema_shelters` | [FEMA open shelters](https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer) | 20 min | No |
| `overpass` | OpenStreetMap fire, police, hospital, pharmacy, ambulance and shelter locations via [Overpass](https://overpass-api.de/) | 24 h | No |
| `dallas_gis` | [City of Dallas](https://gis.dallascityhall.com/arcgis/rest/services/Basemap/CityLimits/MapServer/0) city limits | 24 h | No |
| `openfreemap` | [OpenFreeMap](https://openfreemap.org/) style availability (the browser loads the tiles itself) | 24 h | No |

The internal `community_reports` adapter refreshes every 60 seconds through a protected Spacetime route using the existing ingest credentials. It publishes only coarse-area multi-reporter counts and help types, never raw private request details.

Limit or switch adapters with `ENABLED_SOURCES` in `backend/.env`.

### Collector endpoints

The collector serves read-only JSON on http://127.0.0.1:8000 (interactive docs at `/docs` and `/redoc`, spec at `/openapi.json`). The React app reads from Spacetime, not from these.

| Endpoint | Returns |
| --- | --- |
| `/pins` | Records with coordinates, plus `unlocated` ones; filters `source`, `category`, `kind`, `include_stale`, `limit`, `offset` |
| `/geojson` | Located records as a GeoJSON FeatureCollection |
| `/issues` | Regional issue cards, supporting records and bounded-investigation traces; paginated with `limit` and `offset` |
| `/sources` | Each adapter's status, last success, age, interval, stale flag, record count and error |
| `/health` | Service status plus `spacetime_sync`, `nemotron`, `resident_ai` and `issue_analysis` worker status |
| `/boundaries` | Dallas city limits as GeoJSON |
| `/map-config` | Basemap style, default center, region box and attribution |

Researched but not integrated: DriveTexas, AirNow, NASA FIRMS, DART realtime, ORNL ODIN, ERCOT grid status, IODA, NOAA HMS smoke, Dallas Fire-Rescue active calls, radar tiles. [PROJECT_HANDOFF.txt](PROJECT_HANDOFF.txt) and [API_READINESS.md](API_READINESS.md) record each source's limits and test results.

## Priority and AI

- **Rules (`backend/app/priority.py`):** every alert and incident gets a 1–10 score (10 = most urgent danger) with listed reasons, from fields such as NWS severity/urgency/certainty, storm size and remarks, Dallas police priority and call type, fire acres and containment, and earthquake magnitude. Facilities, shelters and readings are not scored.
- **Nemotron (`backend/app/nemotron.py`):** with a working key, Nemotron receives the rule guidelines and the record, starts from the rules score, and can raise it for clearly critical factors the rules don't list. A raise of 2 or more must quote the record verbatim; lowering is capped at 2; invalid answers keep the rules score.
- **Summaries:** plain-language headlines and summaries are validated (no invented numbers, links or advice). Official NWS instructions are always shown verbatim.

Details and guardrails: [backend/README.md](backend/README.md). Resident AI assessment: [RESIDENT_REPORTING.md](RESIDENT_REPORTING.md).

## Resident requests and shared concerns

Residents submit location, help type, people affected and relevant details. Their individual pins and AI assessments remain visible only to their browser identity. Requests can be withdrawn and expire after 24 hours.

For the hackathon, reported needs are assumed accurate for prioritization, explicitly labeled **Hackathon assumption**. In approximately 5 km cells, two distinct reporter identities produce a Caution concern; three or more produce Active threat. Only the latest active request per identity per cell counts. These are demo thresholds, not validated disaster criteria; identities do not prove distinct people. Counts alone cannot produce Critical or establish a shared cause. A single request stays private and does not produce a shared concern.

Public aggregates refresh every minute and expire after two minutes without renewal. Withdrawal and expiry remove requests from the next aggregate. Exact locations, descriptions, owner identities and individual AI outputs are not copied into the shared feed.

## Responder assessments and investigations

The Responder page shows scrollable cards filtered by **Critical**, **Active threat**, **Caution**, **Informational**, or **Awaiting AI**. Active threat badges and card borders are red. Facilities are excluded from issue synthesis. Rules screen current evidence first; Nemotron proposes the final level within evidence-based limits and supplies exact supporting quotes.

Before final synthesis, Nemotron can identify missing evidence and choose zero to two read-only tools: weather (NWS/IEM), river (NWPS/USGS), or traffic (TomTom). The backend retrieves fresh cached API records within 15 km of the concern, then Nemotron reassesses with validated citations. This uses the shared feed collectors rather than making new upstream requests per investigation. Missing evidence is inconclusive; existing severity bounds still apply.

Investigation questions, selected tools, source status and matching IDs are retained in `/issues` for inspection, but the investigation-step display is hidden from responder cards. Final summaries, uncertainty and expandable evidence remain visible. Workflows share a bounded time budget, and accepted assessments refresh after five minutes. Invalid plans or unsupported citations leave the group awaiting an accepted assessment. No tool can dispatch responders.

See [RESPONDER_ISSUES.md](RESPONDER_ISSUES.md) for implementation details.

## Design system

The UI uses a reusable "liquid glass" system with a Frutiger Aero palette, built to feel like a static page: no looping animations and no live blur by default.

- `src/theme/glass.css`: tokens (color, glass material, radii, spacing, motion, fonts), the static `.aurora` backdrop, surfaces (`.glass`, `.glass--strong`, `.glass--subtle`, `.glass--tint`), controls (`.glass-button`, `.glass-segmented`, `.glass-chip`, `.glass-input`/`.glass-field`, `.glass-badge`, `.glass-dot`) and helpers. Costly effects are opt-in: `.glass--frosted` (live blur), `.aurora--animated`, `.aurora--grain`.
- `src/theme/aero.css`: the sky/aqua/lime palette and glossy finishes. Remove its `@import` in `src/styles.css` to return to the default teal glass.
- Fonts: **Jua** for headings and the brand, **Nanum Gothic** for labels, tabs and buttons, **Open Sans** for body text (`--font-display`, `--font-label`, `--font-sans`).
- Light and dark mode follow the system setting; force one with `data-theme="light"` or `"dark"` on `<html>`.

## Testing

```powershell
# Backend unit tests (mocked network)
cd backend; .venv/Scripts/python.exe -m pytest -q

# One live fetch per enabled feed, without touching the running service's cache
cd backend; .venv/Scripts/python.exe smoke_check.py

# Spacetime module tests
cd spacetimedb; npx vitest run

# Frontend type-check and build
npm run build
```

`test/check_endpoints.py` checks every collector endpoint against a running API and prints a PASS/WARN/FAIL report that is safe to share: `backend/.venv/Scripts/python.exe test/check_endpoints.py`. The `test/` folder is gitignored for local checks.

## Changing the Spacetime module

Requires the [SpacetimeDB CLI](https://spacetimedb.com/install) and the database owner's login.

1. `npm install --prefix spacetimedb`
2. Edit `spacetimedb/src/index.ts` (tables, reducers, views, HTTP routes).
3. Regenerate bindings after every schema change: `npm run spacetime:generate`
4. Publish: `npm run spacetime:publish` (Maincloud) or `npm run spacetime:publish:local` (after `spacetime start`).

Database `texas-response-zl8x2` runs on Maincloud. Ingestion, routes and secret rotation are documented in [SPACETIME_INTEGRATION.md](SPACETIME_INTEGRATION.md).

## Project layout

```text
src/
  App.tsx, main.tsx            Shell, tabs, optional Spacetime provider
  screens/                     Resident and Responder active screens
  components/LiveMap.tsx       Spacetime subscriptions, layer toggles, feed status
  components/DallasMap.tsx     MapLibre map, pin styling and popups
  components/ResidentReports.tsx  Resident request form and history
  theme/glass.css, aero.css    Reusable design system and palette
  module_bindings/             Generated Spacetime bindings (do not edit)
spacetimedb/src/index.ts       Tables, reducers, views, HTTP ingest routes, expiry schedule
backend/app/
  main.py                      Collector, adapters, REST endpoints
  priority.py, nemotron.py     Rule priority, AI summaries and priority decisions
  resident_ai.py, issues.py    Private resident assessments, regional issue cards
  investigation.py             Bounded Nemotron tool planning and evidence retrieval
  community.py                 Anonymous community-summary adapter
  extra_feeds.py, tomtom.py    311, EONET and TomTom adapters
  spacetime_sync.py, water_risk.py  Ingest bridge, gauge flood assessment
backend/tests/                 Backend unit tests
scripts/start-services.ps1     Used by start-app.bat
public/data/                   Dallas city-limits snapshot
test/                          Local endpoint checker (gitignored)
```

## Data rules

- Label records as observed, reported, forecast or inferred, and show when they were updated.
- No data means unknown, not safe. A low priority score never means an area is safe.
- A reported hazard doesn't prove someone needs help, and a disappearing call doesn't prove it was resolved.
- A driving estimate is never an emergency response ETA.
- Resident locations, contact details, medical and accessibility needs, and responder movement stay private.
- Human review is required for consequential decisions. Assignment, resolution tracking and dispatch are not implemented; Nemotron proposes assessments.
- Text from external feeds is untrusted data, never instructions for the AI.

## More documentation

- [SPACETIME_INTEGRATION.md](SPACETIME_INTEGRATION.md): Maincloud database, ingestion, subscriptions, secrets
- [backend/README.md](backend/README.md): collector endpoints, adapters, caching, geocoding, priority and Nemotron
- [RESIDENT_REPORTING.md](RESIDENT_REPORTING.md): resident requests, privacy, expiry and AI assessment
- [RESPONDER_ISSUES.md](RESPONDER_ISSUES.md): shared issue synthesis, bounded investigations and guardrails
- [API_READINESS.md](API_READINESS.md): anonymous API test results
- [PROJECT_HANDOFF.txt](PROJECT_HANDOFF.txt): goals, scope, sources and build order
- [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md): SpacetimeDB rules for coding agents

## Attribution

Basemap © [OpenFreeMap](https://openfreemap.org/) and © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors. City limits from City of Dallas GIS Services. Feed data belongs to its providers; keep attribution visible as layers are added. Fonts from Google Fonts.

## License

[Apache License 2.0](LICENSE).
