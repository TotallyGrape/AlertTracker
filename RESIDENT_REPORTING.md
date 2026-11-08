# Resident assistance reporting and Nemotron

## Hackathon integration into the main feed

Active resident requests now contribute **anonymous coarse-area aggregates** to the public map and shared issue synthesis through source `community_reports`. The original owner identity, exact coordinates, address/landmark, title, description, and private AI assessment are not copied to that source. The form discloses aggregate use. Individual requests and their exact pins remain private.

Every minute, a credential-checked Spacetime route computes approximately 5 km cells from active requests less than 24 hours old. It selects only the latest request per authenticated connection identity per cell and suppresses cells with fewer than two distinct identities. This prevents repeated submissions from one identity inflating a cluster, but anonymous identities do not prove distinct humans or prevent Sybil abuse. This is a hackathon assumption, not a production verification system.

The shared pin states report counts, help-type counts and a coarse cell center. The model treats the reported needs as accurate **for demo prioritization**, with “Hackathon assumption” explicitly shown on resulting issue titles. Two reporter identities set a Caution floor/cap; three or more set Active threat. These thresholds are demo heuristics, not scientifically validated hazard thresholds. Community counts alone cannot establish Critical, an independently verified event, a shared cause, or automatic dispatch.

Aggregates use a two-minute expiry and are recomputed every minute. Withdrawn/expired requests are excluded on the next refresh, and successful empty results clear the previous aggregate pins. Shared issue cards follow the existing refresh/expiry pipeline. To test, submit active requests in the same area from two different browser identities; additional submissions from the same identity count once. Single requests remain private and do not create a public cluster.

## Map pins and expiry

Each submitter's active requests appear as purple pins on their own map, enabled by default through “Your active requests.” Pin popups include the unverified request text, people affected, AI suggestion when available, and submission/expiry times. These are read from the owner-filtered `my_reports` view; they are not made public or copied into the external incident feed.

A request has a fixed 24-hour lifetime from submission. Withdrawal, expiry, or any non-submitted status removes it from the map. The map rechecks age every 30 seconds, even when the collector is offline; an open popup closes when its pin disappears. A private Spacetime schedule runs every minute to mark submitted reports older than 24 hours expired and cancel unfinished AI work. The schedule runs independently of Python and survives app restarts. History is retained privately, and no automatic renewal occurs. Submit a new request if assistance is still needed. Existing active submissions use the same lifetime from their original creation time.

The idempotent `ensure_report_expiry` reducer installs the timer on an existing database and performs an expiry pass; it was invoked during deployment. Fresh databases install it through `init`. Tests cover the exact 24-hour map boundary, withdrawn pins, stored expiry, cancellation of queued AI, private history retention and idempotent timer creation.

The Resident tab now saves a title, assistance category, number of people affected (1–1000), relevant details, address/landmark, and Greater Dallas coordinates. The optional “Use my location” button requests browser location only when clicked; residents must confirm that it is where help is needed. Manual coordinates remain available. Submissions use the `submit_assistance_request` reducer and the authenticated connection's `ctx.sender` as owner. Validation and the existing 30-second submission limit/ten-open-request limit run server-side.

Data lives in the private Spacetime `resident_report` table. The `my_reports` view exposes only the caller's rows, including AI results. Reports are not copied into public incident tables, map feeds, or the FastAPI `/pins` endpoint. The current identity is stored in the browser; production sign-in/account recovery and coordinator/responder roles remain future work.

Request progress and AI progress are separate. A submitted request displays “Submitted — awaiting human review.” AI progresses through queued, processing and complete, with a failed/unavailable state if all retries fail. Withdrawal cancels outstanding assessment work; a late result cannot update a withdrawn report. AI completion does not imply a person has reviewed, accepted or dispatched help. Coordinator assignment and resolution are not implemented by this change.

## Private AI workflow

FastAPI starts `app.resident_ai.run()` alongside the existing feed and Nemotron workers. It uses the existing NVIDIA settings and the private ingestion credential. Every 15 seconds it claims at most two pending jobs through the credential-checked Spacetime HTTP route:

- `POST /v1/database/texas-response-zl8x2/route/resident-ai/claim`
- `POST /v1/database/texas-response-zl8x2/route/resident-ai/result`

These are Spacetime routes, not public FastAPI endpoints. Both require `x-ingest-secret`. Jobs have a three-minute lease and at most three attempts. Results must match the current claim lease, preventing a superseded worker from replacing a newer result. Worker failures never remove the resident's request. The worker does not create a local disk cache of resident text.

Only title, details, assistance type and people count are passed to NVIDIA for assessment. Structured address/landmark, coordinates and owner identity are excluded. Information voluntarily included in the title/details will still be processed by NVIDIA; the form advises against unnecessary personal/contact details. The page discloses the processing before submission.

Nemotron returns a summary, suggested urgency (`low`, `medium`, `high`, `critical`), short reasons and a supporting quote. The original report stays visible. The prompt treats resident text as untrusted data, prohibits invented conditions/assignments/treatment instructions, and labels urgency as an unverified suggestion for human review. Validation checks the response shape, lengths, numeric claims and quoted evidence; high/critical assessments require an actual quote. Invalid results retry within the attempt limit. These checks reduce malformed/unsupported output; they do not prove the AI's interpretation is correct.

`GET http://127.0.0.1:8000/health` includes `resident_ai` status, completion/failure counts and sanitized error types. Keep FastAPI running for processing; saved requests remain accessible through Maincloud if it is offline. AI assessment currently uses the resident's report only; no automatic nearby-feed corroboration is claimed.

## Compatibility and verification

The deployment appended migration-safe defaults without deleting reports. Old reports remain accessible with AI “not requested.” The original `submit_report` reducer remains available for legacy clients/tests and does not trigger AI. Generated client bindings were updated for the expanded view and new reducer. Existing browsers may need a refresh after this view-schema update.

Verified: frontend production build, four module datastore tests, 59 backend tests, and a live simulated request processed by Nemotron and visible only to its submitting identity. The simulated request was withdrawn after verification. Tests cover invalid counts/categories/location text, ownership, evidence validation and malformed AI output. Existing two-identity privacy and private-table access checks remain in the live suite.

Run `start-app.bat` to launch the app. The new worker needs no additional dependency, API key, database, or process beyond the existing setup.
