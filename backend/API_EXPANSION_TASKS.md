# Backend feed expansion

Frontend changes are explicitly deferred. Existing REST response fields remain compatible.

Implement sequentially:

- [x] TomTom: key supplied later; adapter implemented and live-tested (840 regional traffic records). Polls every 15 minutes, splits the DFW region into two requests and deduplicates IDs. Frontend changes remain deferred.
- [x] NASA FIRMS: blocked by missing FIRMS_MAP_KEY; skipped.
- [x] AirNow: blocked by missing AIRNOW_API_KEY; skipped.
- [x] Dallas 311: anonymous recent open hazard reports, stable IDs, supplied coordinates and bounded pagination. Live check: 49 located reports after removing routine/planned work.
- [x] NASA EONET: anonymous regional events, latest geometry and date filtering. Live check: successful empty result for DFW.
- [x] Register source intervals. Missing-key services are skipped; TomTom is now enabled after its key was supplied and uses credential-safe errors.
- [x] Extend Spacetime ingestion source allowlist without changing frontend bindings/schema; existing health statuses remain sufficient.
- [x] Run backend tests: 51 passed after TomTom integration. Compatible module update published with --delete-data=never.
- [x] Restart Python and verify REST/source health and Maincloud synchronization: 49 active dallas_311 rows; both new sources ok and not stale.
- [x] Document coverage/freshness, blocked sources and deferred frontend work in backend/README.md and this task list. No keys were acquired or accounts registered.

Credential audit: TOMTOM_API_KEY, FIRMS_MAP_KEY and AIRNOW_API_KEY must be checked without printing their values. Never create provider accounts or request keys automatically.

## Deferred frontend work (do not implement until requested)

- Add dedicated filters/legends for community infrastructure reports and curated natural events.
- Replace the existing hard-coded `/12` source count with a dynamic denominator (backend now has 15 enabled sources by default).
- Clearly surface publication delay, reported status, observation time, and duplicate/overlap across sources.
- Decide whether/how Nemotron should summarize or prioritize these additional source types; no AI dispatch or new scoring policy is added here.

No frontend source files or client bindings were modified by this task. Existing generic subscriptions may already receive the added incident rows; there is no new UI implementation.
