# Responder issue synthesis

Update: `community_reports` now supplies anonymous multi-reporter counts to the main synthesis, with an explicit **hackathon assumption** rather than verified status. No private descriptions, identities, exact coordinates or individual resident AI outputs are shared. Two identities in a coarse area produce Caution; three or more Active threat, never Critical from counts alone. See RESIDENT_REPORTING.md for aggregation, expiry and demo limitations. This supersedes the earlier statement below that resident signals are completely excluded: private rows remain excluded, but their coarse anonymous multi-reporter counts now contribute.

The Responder tab now contains a scrollable, filterable feed of coherent issue cards: Critical, Active threat, Caution and Informational. Cards explicitly distinguish accepted Nemotron assessments from rule-screened groups awaiting AI. Each includes uncertainty, location (or unknown), timestamps, original evidence, input priority scores, citations/quotes, rule limits and measured trends when available. Cards do not dispatch help or assert human verification.

## Rules first, Nemotron second

The FastAPI `app.issues` worker scans **all cached public non-resource records**, independently of map checkboxes, the map viewport and the narrower facility/reading display circle. It excludes stale sources, expired events, older water/incident observations and future observations. All resource/facility rows are excluded. Source IDs deduplicate within groups. Unlocated records are kept in separate groups rather than assigned fictional positions.

It groups compatible hazard families into fixed approximately 3 km cells. These are evidence groups, not claims that all reports describe one incident. Official warning polygons are also attached to compatible groups whose evidence points lie inside them. Fixed cells can split nearby evidence across boundaries; broad hazards can support multiple cards. Cross-provider records are not automatically treated as independent witnesses, and no high-confidence numerical probability is invented.

All accepted evidence contributes to grouping and counts. Each AI payload includes up to 12 selected records, ranked by existing priorities (including validated Nemotron priorities when available), plus total counts and measured trends. The full group ID list is retained. This bounds context length; the UI discloses sampling. “All pins scanned” does not mean each full record is sent on every AI request.

Rules derive an allowed threat range. Official high-urgency warnings and NOAA gauge flooding/action categories establish floors. Routine gauges/forecasts alone cannot become active threats; traffic congestion or construction alone cannot become Critical. Critical escalation requires urgent supporting source evidence, not simply multiple nearby pins or a model score. Nemotron selects a level and writes a synthesis within those limits; out-of-range levels are clamped and the card discloses the adjustment.

Nemotron must return bounded JSON with actual source IDs and exact supporting quotes. Validators reject unknown citations, fabricated quotes/numbers, markup/URLs, unsupported harm claims and assertions of confirmation/dispatch. These checks constrain errors but do not prove the model's interpretation: every AI card remains an unverified concern requiring human review. Prompt injection in source text is treated as untrusted data.

Issue synthesis explicitly requests JSON-object mode with thinking disabled so reasoning text cannot displace the final structured result. Other existing priority/resident AI workflows retain their own reasoning settings. The synthesis prompt/cache version changes when its request contract changes, avoiding reuse of invalid old responses.

## Trends, refresh and failure

The worker retains up to 24 water-stage samples per series for six hours in the ignored backend cache. A directional trend requires at least three distinct observation times, a consistent unit and at least 15 minutes of observations. Duplicate polls do not add samples. Rising measurements are not automatically flooding, and unknown thresholds remain unknown. Event clusters are not labeled “increasing” without actual trend evidence. Forecasts are not presented as observed conditions.

There are at most six new model jobs per cycle, with a 55-second aggregate inference budget and a 30-second pause between cycles. Unchanged evidence reuses cached model results; failed/rejected results wait ten minutes before retry unless the evidence changes. Large backlogs remain visibly pending rather than fabricated as completed AI work. Changed/stale evidence is re-evaluated before publication. The cards retain model and generation time. Records are refreshed centrally rather than per browser viewer.

Each published card has a five-minute lease. Stopped/failed analysis therefore ages out of the UI; expired card rows are also pruned by the existing minute-level Spacetime cleanup. Refreshing the source snapshot removes vanished groups. Frontend filters offer all four levels and the scrolling feed initially renders 40 cards, with a “Show more” button; all groups remain available.

## Spacetime and API

`issue_card` is a public table containing IDs, payload JSON and expiry. Only the credential-checked `/v1/database/texas-response-zl8x2/route/issues` HTTP handler writes issue snapshots. Snapshots replace the current set atomically and reject malformed IDs, levels, statuses, duplicate IDs and expired timestamps. React subscribes directly through generated bindings. No credentials reach the browser.

FastAPI `GET /issues?limit=50&offset=0` exposes cached cards, total and analysis status (limit 1–200). `/health` includes `issue_analysis`: scanned/excluded records, candidates, accepted AI count and the most recent error type. These GETs do not trigger model or provider calls.

Private resident requests are **never included in public shared synthesis**. A separate section on the Responder tab displays only the current identity's active private requests and their existing resident-specific Nemotron assessments. It uses the owner-filtered view and respects the 24-hour lifetime. Until responder/coordinator permissions are implemented, tabs do not grant access to other people's requests.

## Validation

Backend tests cover facilities/stale/expired exclusions, ID deduplication, spatial/hazard separation, quote/citation validation, severity clamping/floors, unsupported claims, measurement-history requirements and stable cache fingerprints. Existing module privacy/expiry tests and frontend production build are also run for this feature. Live rollout verifies actual model-generated cards and their Maincloud subscription.

Verification: 66 backend tests, six module/pin tests, and frontend production build pass. Live synthesis scans approximately 1,000 non-resource records into several hundred groups; validated Nemotron cards have been observed in the API. Invalid outputs remain unassessed, and a large backlog populates gradually. Explicit negative uncertainty such as “not independently verified” is accepted; positive confirmation and unsupported safety assertions are rejected. Threat-category filter counts cover accepted model classifications; “Awaiting AI” separately lists unassessed/rejected groups.

No extra API key or process is required: `start-app.bat` launches the existing services, and FastAPI starts the new worker automatically using existing NVIDIA and Spacetime configuration.


## Bounded Nemotron investigation

Before final synthesis, Nemotron returns a validated plan containing a missing-evidence question and zero to two tool names: weather, river, traffic. The backend executes those read-only queries over continuously refreshed external API snapshots within 15 km of the original concern. These are cached API evidence tools, not new upstream HTTP calls per investigation. Weather queries NWS alerts/forecasts and IEM; river queries NWPS and USGS; traffic queries TomTom. Stale sources, expired records and unsupported observation ages are rejected by the existing screening rules. Up to six evidence records per tool are added to the final model input. Empty results are explicitly inconclusive.

The final Nemotron assessment must cite actual original/tool evidence IDs and exact quotes. Existing severity floors/caps remain in force: contextual records do not silently override the original concern's limits. Invalid plans, tool names, citations or assessments fail closed to Awaiting AI; no dispatch is possible. The whole planning/tool/synthesis workflow shares the worker's 55-second cycle budget. Accepted assessments refresh after five minutes. Cards show the question, chosen checks, source status, check time, matching IDs and final cited assessment. The planner may choose no checks when none are relevant.

Deployment: backend restarted locally; Vite serves the updated card UI. No Spacetime schema migration or new key is required; issue payload JSON carries the investigation trace.
