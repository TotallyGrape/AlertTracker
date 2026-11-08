# Public API readiness check

Test date: November 7, 2026. All requests were anonymous: no login, API key, signup, or access application. This is a point-in-time backend HTTP smoke test, not an uptime guarantee, full browser integration test, or proof of complete DFW coverage.

| Source | Result | Remaining work / limitations |
|---|---|---|
| NWS alerts and weather | HTTP 200 for Texas active alerts, Dallas point discovery, and Dallas forecast | Set identifying User-Agent, cache and respect limits. Some alert geometries are null: resolve affected zones. |
| NOAA NWPS | HTTP 200; Trinity River at Dallas observation and thresholds returned | Forecast marked not current with missing-value sentinels in this response. Handle absent forecasts. Collect centrally on backend. |
| USGS Water | HTTP 200; three DFW-area latest-continuous observations returned | Some latest series values are old, including an inactive series from 2015. Filter desired parameters and observation age; paginate. |
| Dallas police | HTTP 200; three active records and dataset metadata returned | Samples have street/block descriptions, not coordinates. Need geocoding or spatial reference matching for map placement. Only releasable on-scene incidents; intermittent-delay warning remains. |
| IEM | HTTP 200, valid GeoJSON | Correct office filter is wfos=FWD, not wfo=FWD. Corrected recent-window query returned zero reports; empty does not mean failure or safety. Apply geographic filters as well. |
| NIFC WFIGS | HTTP 200; perimeter record returned nationally, DFW spatial count query succeeded | Zero records in tested DFW envelope. Map perimeter timestamps, not just service refresh times. |
| USGS earthquakes | HTTP 200; 169 events in past-day national feed | Filter DFW/nearby geography and severity. Initial events may be revised. |
| FEMA shelters | HTTP 200; metadata and two shelter features nationally | DFW spatial count was zero. Capacity and accessibility fields were null in samples. Do not infer availability or absence of all local shelters. |
| Dallas GIS | HTTP 200; official Dallas polygon returned | Municipal border, not metropolitan boundary. Backend fetch/local snapshot avoids direct-browser cross-origin uncertainty. Already used in app. |
| OpenFreeMap | HTTP 200 for style, vector TileJSON, and sprite metadata | Already rendered successfully in app in prior browser QA. Preserve attribution; no SLA. No key needed. |
| Overpass | HTTP 200; three Dallas fire-station objects returned | About 31 seconds in this test. Use background imports/cache, not synchronous page loads. One returned object has historic-station metadata; verify active operational status. |

Human intervention: none needed to obtain the tested public data. Human verification/partnership still needed for operational response availability, shelter suitability/capacity, and any actual agency dispatch. Geocoding police records and validating facilities are implementation/data-quality work; this test does not supply a new free geocoding service.

Implementation recommendation: ingest centrally through the backend. A server request succeeding does not prove cross-origin browser access. No need for each browser to poll every feed.

Raw results and exact tested URLs:
- api-readiness-results.json
- api-readiness-followup.json

Rerun scripts:
- python api_readiness_check.py
- python api_readiness_followup.py

The scripts use a fixed time window matching this test date for IEM; change it before a later rerun. The first script intentionally records an initial incorrectly singular wfo filter; the corrected wfos query is in the follow-up. Always use the corrected form for integration.
