# Dallas Disaster Feed API

Independent Python/FastAPI service for the Texas Response project. It collects public feeds into normalized map records for a configurable Greater Dallas rectangle. No SpacetimeDB database, AI model, API key or frontend build is required for its standalone REST endpoints.

**Integration update:** the optional Spacetime bridge is now implemented and configured locally. The frontend subscribes to Maincloud rather than calling this REST API. See `../SPACETIME_INTEGRATION.md` for the current architecture, security, configuration and verification; the "Future frontend connection" section below describes the original REST-only contract. Standalone REST operation still works without Spacetime environment settings.

## Start

From the repository root in PowerShell:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Python 3.11+ recommended; tested with Python 3.14 on Windows. On Linux/macOS use `.venv/bin/python` instead. Run one worker: every worker would independently poll providers. Stop with Ctrl+C. A reload restarts the pollers; the disk cache avoids unnecessary initial refetches.

- Interactive documentation: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json
- Pins: http://127.0.0.1:8000/pins
- Source health: http://127.0.0.1:8000/sources

Optional: copy `.env.example` to `.env` inside **backend**. This is separate from the frontend environment. Set a contact-bearing `UPSTREAM_USER_AGENT` for NWS use. `BBOX` is west,south,east,north and defaults to `-97.65,32.45,-96.25,33.3`, an approximate DFW rectangle, not an official metro boundary. `NWPS_GAUGES` defaults to `dalt2`; additional comma-separated gauge IDs expand that source. `ENABLED_SOURCES` selects a comma-separated subset of adapter names. Restart after changing configuration. No registration or credentials are required by the configured public endpoints.

## Endpoints

| GET path | Response/use |
| --- | --- |
| `/pins` | `pins`, `unlocated`, totals, pagination, bbox, generated timestamp and source status |
| `/geojson` | FeatureCollection of located records, preserving original area geometry; max 10,000 with `truncated` flag |
| `/sources` | Per-source status, last attempt/success, age, interval, errors, stale flag and cached record count |
| `/health` | Process liveness plus aggregate `ok`/`degraded`; HTTP 200 means process is serving, not all feeds healthy |
| `/boundaries` | Dallas city-limits FeatureCollection and source status |
| `/map-config` | OpenFreeMap style URL, default center, bbox, attribution and relative data URLs |

`/pins` query parameters: `source`, `category`, `kind` (exact string filters), `include_stale=true`, `limit=1000` (1–10,000), `offset=0`. Pagination independently applies to `pins` and `unlocated`; consult both totals. Unknown filter strings produce empty results. Ordering is source name then provider order; do not treat pagination as a permanent snapshot during refreshes. `/geojson` optionally filters by `source`.

Example pin (illustrative, not a live warning):

```json
{
  "id": "nws_alerts:provider-id",
  "source": "nws_alerts",
  "name": "Flash Flood Warning",
  "description": "Provider's warning text",
  "kind": "warning",
  "category": "flood",
  "latitude": 32.8,
  "longitude": -96.8,
  "geometry": {"type": "Point", "coordinates": [-96.8, 32.8]},
  "location_accuracy": "source_point",
  "updated_at": "2026-11-07T20:00:00+00:00",
  "observed_at": null,
  "expires_at": "2026-11-07T21:00:00+00:00",
  "source_url": "https://api.weather.gov/alerts/provider-id",
  "attributes": {},
  "fetched_at": "2026-11-07T20:01:00+00:00",
  "stale": false
}
```

`kind` is `warning`, `incident`, `observation`, `forecast`, or `resource`. A normal river reading or a hospital is not a danger alert. Categories are descriptive, not a severity score. IDs include the provider namespace; cross-provider events are not deduplicated or AI-validated. Nullable timestamps mean the provider did not supply a usable timestamp. `fetched_at` is acquisition time, never proof the underlying observation is current. `attributes` vary by source.

GeoJSON uses `[longitude, latitude]`. Point records use source coordinates; area records keep the provider's full Polygon/MultiPolygon and use a representative point **within its intersection with the configured region** as the pin. There is no fabricated impact radius. Original polygons can extend outside the rectangle. NWS zone polygons are used if an alert lacks direct geometry; their shape represents the alert zone, not a precise damage footprint. Records lacking location remain in `unlocated` with null coordinates and geometry. Those cannot be rendered as pins until a reliable location is supplied.

## Coverage and polling

| Adapter | Default interval | Data and limits |
| --- | --- | --- |
| `nws_alerts` | 60 s | Active Texas NWS alerts, spatially filtered; missing geometry resolved from affected NWS zones |
| `nws_weather` | 15 min | Forecast for the central Dallas grid only, not weather coverage at every location |
| `nwps` | 5 min | NOAA river observations and flood thresholds for configured gauges; initially Trinity at Dallas |
| `usgs_water` | 5 min | Regional latest streamflow and gauge-height observations; rejects readings older than 6 hours |
| `dallas_police` | 2 min | Dallas published active police calls, deduplicated by incident. Street text is geocoded with the City of Dallas street locator (score ≥ 90, block or intersection matches only, cached in `.cache/police_geocodes.json`, at most 60 new lookups per poll). `location_accuracy` is `geocoded_block` or `geocoded_intersection`; freeway direction may be wrong. Weak or failed matches stay unlocated |
| `iem` | 5 min | Last 24 hours of preliminary local storm reports from FWD, filtered to rectangle |
| `nifc` | 10 min | Published regional current interagency fire perimeters; verify age/type/current conditions |
| `earthquakes` | 60 s | USGS past-day earthquake feed, spatially filtered; points only, no shaking footprint |
| `fema_shelters` | 20 min | Published regional shelters; status/capacity must be independently confirmed |
| `dallas_gis` | 24 h | Official Dallas city boundary; does not create hazard pins |
| `openfreemap` | 24 h | Checks style availability; frontend loads actual map tiles directly |
| `overpass` | 24 h | Bulk OSM fire/police/hospital/shelter/pharmacy/ambulance locations, all availability unverified |

Public police data is not a live 911/dispatch feed and does not cover every city or incident. Facilities do not imply personnel, vehicles or beds are available. There are no utility outage, traffic, EMS dispatch, chemical release, missing-person or user-report feeds in this implementation. A disaster type may be covered through an NWS alert without having a dedicated sensor feed. Empty results never mean the area is safe.

## Caching and failures

Background tasks poll each adapter independently using one shared HTTP client with at most eight connections. GET endpoints read memory and do not trigger upstream requests. Successful snapshots persist under `backend/.cache`; same-bbox snapshots reload on restart. Successful empty results replace prior records. Failures retain the last good snapshot and mark its records stale. Staleness also applies after twice the configured interval. `include_stale=false` suppresses stale records. Expired alerts/forecasts, river readings older than six hours and storm/earthquake observations older than 24 hours are excluded even if cached. Providers without event timestamps cannot be freshness-verified.

First startup responds immediately and fills feeds asynchronously, so `/health` initially reports degraded and `/pins` can be empty. Check `/sources` before interpreting results. Network failures retry at the next scheduled interval. Pagination is bounded; exceeding its limit fails that refresh rather than silently installing a partial snapshot. There is no externally callable refresh endpoint. Geometry or provider-schema failures can fail an adapter refresh; its prior snapshot is retained. Polling is a hackathon starter, not a guaranteed emergency notification service.

## Future frontend connection (recorded contract)

- Backend origin: `http://127.0.0.1:8000`; frontend stays `http://localhost:5173`.
- Default CORS permits localhost and 127.0.0.1 on port 5173. Configure `CORS_ORIGINS` for another origin. CORS is not authentication.
- Fetch `/pins` for list/details and pin locations. Fetch `/geojson` for MapLibre GeoJSON layers; use fill/line layers for polygons and circle/symbol layers for points. Keep source health visible and style resources separately from hazards.
- Keep OpenFreeMap and the existing Dallas boundary integration; these do not need to be proxied through Python.
- No frontend URL/configuration files have been changed. Future integration may introduce `VITE_DISASTER_API_URL=http://127.0.0.1:8000`.
- No automatic SpacetimeDB or Nemotron connection yet. Later ingestion/synchronization must run outside deterministic reducers; never put external fetches inside reducers.
- Service currently exposes read-only unauthenticated endpoints bound to loopback. Add deployment-specific authentication, rate controls and HTTPS before exposing publicly. Treat upstream descriptions as untrusted text and avoid rendering raw HTML.

## Verification

From `backend`:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe smoke_check.py
```

Unit tests use mock transports and cover geometry, out-of-region filtering, expired data, police deduplication/unlocated records, old river readings, source failure/cache retention, endpoint validation and GeoJSON. The smoke check fetches all enabled adapters once, prints per-source counts/errors and does not start polling or modify the service cache. Live feeds may legitimately return zero events and may intermittently fail or throttle requests.

Verified November 7, 2026: all 12 adapters succeeded in a live smoke check; 105 recent USGS water records, one NOAA river record, one Dallas forecast, 3,345 OSM facilities, 36 unlocated police incidents and one Dallas boundary were returned. Other regional hazard/shelter feeds returned zero matches. These counts change over time. Five automated tests passed. All seven documented endpoint paths and frontend CORS were checked over localhost HTTP. `requirements.lock.txt` records the installed versions; install it with `pip install -r requirements.lock.txt` to reproduce this Windows environment. The test runner currently emits a dependency deprecation warning about Starlette's HTTPX TestClient; tests still pass.

## Nemotron summaries (optional)

`app/nemotron.py` adds plain-language headlines and short summaries to alerts and incidents. It runs beside the pollers and never blocks them.

- **Configure** in `backend/.env`: `NVIDIA_API_KEY` (hosted keys from build.nvidia.com start with `nvapi-`), `NVIDIA_BASE_URL` (default `https://integrate.api.nvidia.com/v1`; any OpenAI-compatible endpoint, such as a self-hosted NIM, works) and `NEMOTRON_MODEL` (default `nvidia/nemotron-3-super-120b-a12b`). `NEMOTRON_REASONING_EFFORT` defaults to `low`; set it empty for endpoints that reject that field. Restart after changing. With no key the worker is disabled and everything else runs normally.
- **What gets summarized:** NWS alerts and storm reports with remarks (headline plus summary), Dallas police call codes and storm report codes (headline only, one call per distinct code, shared by every record with that code), and fire perimeters. Water readings, facilities and earthquakes are not sent.
- **Safety checks:** feed text is sent as JSON data with a system prompt saying it is never instructions. Replies must be exactly `{"headline", "summary"}` within length limits, with no links or markup, and no numbers or number words that are not in the source data. Failed replies are discarded (retried after 24 hours) and the record keeps its original text. Official NWS instructions are always shown verbatim, never AI-written.
- **Cost control:** at most 12 new jobs every 15 seconds, 2 at a time. Results are cached in `.cache/ai_summaries.json`, so restarts do not repeat calls. HTTP 401/403 pauses the worker until restart; 202, 429 and 5xx retry a minute later.
- **Where it shows:** `/pins` and `/geojson` records gain an `ai` object. The Spacetime bridge resends a source when new summaries land, inside the record details, so no module republish is needed. Map popups show the AI headline, an "AI summary · may contain errors" box, and the original text behind "Original text".
- **Status:** `/health` → `nemotron` shows `status`, `model`, `cached`, `pending`, `calls`, `rejected` and `last_error`.

## Priority score (1-10)

`app/priority.py` gives every alert and incident (`kind` `warning` or `incident`) a rule-based `priority` object: `score` 1-10 (10 = most urgent danger), `label` (Low, Moderate, Elevated, High, Critical), `reasons` (each rule that fired, with its points) and `basis` (`rules-v1`). Facilities, shelters, readings and forecasts are not scored.

- **NWS alerts:** event type sets the base (Tornado/Flash Flood Emergency 10, Tornado Warning 9, Flash Flood Warning 8, other warnings 6-7, watches 5-6, advisories 4, statements 3), adjusted by `severity`, `urgency`, `certainty`, damage wording in the text ("particularly dangerous situation", "catastrophic", "destructive", "considerable", "life-threatening") and whether the area includes Dallas.
- **Storm reports:** report type and size (hail inches, wind mph) set the base; remarks mentioning deaths, rescues or people trapped, injuries, structural damage, blocked roads or downed power lines add points; reports older than 6 or 12 hours lose points.
- **Dallas police:** DPD's own priority 1-4 sets the base; call type (shooting, explosion or hazmat, water emergency, assault, robbery, fire, injury, major accident, missing person, disturbance), freeway location and "in progress" add points; calls open over 3 hours lose a point. A single police call is capped at 9.
- **Wildfires:** acres, percent contained and prescribed burns adjust a base of 6. **Earthquakes:** magnitude sets the base; USGS PAGER alert, shaking intensity, felt reports, shallow depth and tsunami flag add points.

Scores are rounded and clamped to 1-10. It is a triage aid, not an official severity, and a low score never means an area is safe. The map sizes pins by score, draws high scores on top, and shows the score with a "Why this priority" list in each popup.

### AI priority decisions (Nemotron)

When `NVIDIA_API_KEY` works, Nemotron makes the final priority decision for every scored alert and incident. Its prompt (`PRIORITY_PROMPT` in `app/nemotron.py`) contains the full rule guidelines (`GUIDELINES` in `app/priority.py`), the record, and the rules score with its reasons. It starts from the rules score, may correct misapplied rules, and raises the score when it finds something clearly critical the guidelines do not list (for example a school, hospital or nursing home, people trapped, a dam or bridge failure, a chemical release, or evacuations). These use `NEMOTRON_PRIORITY_REASONING_EFFORT` (default `high`) and are processed before summaries, highest rules score first.

Guardrails: the reply must be `{"score", "reasons", "critical_factor", "evidence"}` with an integer 1-10 and 1-6 short reasons. A raise of 2 or more needs a `critical_factor` and an `evidence` quote copied exactly from the record. Lowering is limited to 2 below the rules score. Invalid replies, a missing key or an unavailable API leave the rules score in place. The record's `priority.basis` is `rules-v1` or `nemotron:<model>`, and AI decisions keep `rules_score` and `rules_reasons` for comparison. Popups show which one decided and any AI-raised factor with its quote.
