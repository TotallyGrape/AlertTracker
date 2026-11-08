import { schema, table, t, Router, SyncResponse, SenderError } from 'spacetimedb/server';

const incident = table({ name: 'incident', public: true }, {
  id: t.string().primaryKey(), source: t.string().index('btree'), name: t.string(), description: t.string(),
  kind: t.string(), category: t.string(), latitude: t.option(t.f64()), longitude: t.option(t.f64()),
  geometryJson: t.string(), detailsJson: t.string(), active: t.bool(), fetchedAt: t.timestamp(),
});
const sourceHealth = table({ name: 'source_health', public: true }, {
  source: t.string().primaryKey(), status: t.string(), stale: t.bool(),
  lastSuccess: t.option(t.string()), intervalSeconds: t.u32(), error: t.option(t.string()),
  syncedAt: t.timestamp(),
});
const residentReport = table({ name: 'resident_report' }, {
  id: t.u64().primaryKey().autoInc(), owner: t.identity().index('btree'),
  name: t.string(), description: t.string(), latitude: t.f64(), longitude: t.f64(),
  status: t.string(), createdAt: t.timestamp(),
});

// Private database configuration, read in procedures as `ctx.env.NAME`.
// Values are supplied when the module is published; they are never part of
// this source file or the built bundle. Every key is optional so the module
// can publish before all sign-ups are done: a procedure should check for
// `undefined` and mark that source as "missing key" in its health row.
//
// Never pass these values to clients, reducer arguments, logs, or table rows.
const spacetimedb = schema(
  { incident, sourceHealth, residentReport },
  {
    env: {
      INGEST_SECRET: t.string().optional(),
      // NVIDIA hosted Nemotron (Authorization: Bearer ...)
      NVIDIA_API_KEY: t.string().optional(),
      // Road closures and conditions
      DRIVETEXAS_API_KEY: t.string().optional(),
      // Air quality
      AIRNOW_API_KEY: t.string().optional(),
      // NASA FIRMS heat detections (sits in the URL path)
      FIRMS_MAP_KEY: t.string().optional(),
      // DART realtime transit
      DART_API_KEY: t.string().optional(),
      // Optional higher limits
      USGS_API_KEY: t.string().optional(),
      SOCRATA_APP_TOKEN: t.string().optional(),
      // Not secret: NWS requires an identifying User-Agent with contact info
      NWS_USER_AGENT: t.string().optional(),
    },
  }
);
export default spacetimedb;

// Read-only feed tables are written only through the credential-checked HTTP route.
const allowedSources = new Set(['nws_alerts', 'nws_weather', 'nwps', 'usgs_water', 'dallas_police', 'iem', 'nifc', 'earthquakes', 'fema_shelters', 'dallas_gis', 'openfreemap', 'overpass']);
type FeedRecord = {
  id: string; source: string; name: string; description: string; kind: string; category: string;
  latitude: number | null; longitude: number | null; geometry: unknown; [key: string]: unknown;
};
type IngestBody = { source: string; records?: FeedRecord[]; health: {
  status: string; stale: boolean; last_success: string | null; interval_seconds: number; error: string | null;
} };
function sameSecret(actual: string, expected: string) {
  let difference = actual.length ^ expected.length;
  for (let i = 0; i < expected.length; i++) difference |= (actual.charCodeAt(i) || 0) ^ expected.charCodeAt(i);
  return difference === 0;
}
export const ingest = spacetimedb.httpHandler((ctx, request) => {
  const secret = ctx.env.INGEST_SECRET;
  if (!secret || !sameSecret(request.headers.get('x-ingest-secret') ?? '', secret))
    return new SyncResponse('Unauthorized', { status: 401 });
  try {
    const text = request.text();
    if (text.length > 12_000_000) return new SyncResponse('Payload too large', { status: 413 });
    const body = JSON.parse(text) as IngestBody;
    if (!allowedSources.has(body.source) || !body.health || typeof body.health.stale !== 'boolean' ||
        !['ok', 'error', 'pending', 'cached'].includes(body.health.status) ||
        !Number.isInteger(body.health.interval_seconds) || body.health.interval_seconds < 1 ||
        (body.health.last_success !== null && !Number.isFinite(Date.parse(body.health.last_success))) ||
        (body.records !== undefined && (!Array.isArray(body.records) || body.records.length > 10000)))
      throw new Error('Invalid source snapshot');
    const ids = new Set<string>();
    for (const row of body.records ?? []) {
      if (row.source !== body.source || typeof row.id !== 'string' || !row.id.startsWith(body.source + ':') || ids.has(row.id) ||
          !['name', 'description', 'kind', 'category'].every(k => typeof row[k] === 'string') ||
          !(row.latitude === null && row.longitude === null ||
            typeof row.latitude === 'number' && Number.isFinite(row.latitude) && Math.abs(row.latitude) <= 90 &&
            typeof row.longitude === 'number' && Number.isFinite(row.longitude) && Math.abs(row.longitude) <= 180))
        throw new Error('Invalid feed record');
      ids.add(row.id);
    }
    ctx.withTx(tx => {
      if (body.records !== undefined) {
        for (const old of tx.db.incident.source.filter(body.source)) {
          if (!ids.has(old.id) && old.active) tx.db.incident.id.update({ ...old, active: false });
        }
        for (const row of body.records) {
          const { geometry, ...details } = row;
          const value = { id: row.id, source: row.source, name: row.name, description: row.description,
            kind: row.kind, category: row.category, latitude: row.latitude ?? undefined, longitude: row.longitude ?? undefined,
            geometryJson: JSON.stringify(geometry ?? null), detailsJson: JSON.stringify(details), active: true, fetchedAt: tx.timestamp };
          const old = tx.db.incident.id.find(row.id);
          if (!old) tx.db.incident.insert(value);
          else if (!old.active || old.detailsJson !== value.detailsJson || old.geometryJson !== value.geometryJson)
            tx.db.incident.id.update(value);
        }
      }
      const state = { source: body.source, status: body.health.status, stale: body.health.stale,
        lastSuccess: body.health.last_success ?? undefined, intervalSeconds: body.health.interval_seconds,
        error: body.health.error ?? undefined, syncedAt: tx.timestamp };
      if (tx.db.sourceHealth.source.find(body.source)) tx.db.sourceHealth.source.update(state);
      else tx.db.sourceHealth.insert(state);
    });
    return new SyncResponse(JSON.stringify({ accepted: true, records: body.records?.length ?? null }), { headers: { 'content-type': 'application/json' } });
  } catch {
    return new SyncResponse('Invalid ingestion snapshot', { status: 400 });
  }
});
export const routes = spacetimedb.httpRouter(new Router().post('/ingest', ingest));

export const submitReport = spacetimedb.reducer({ name: t.string(), description: t.string(), latitude: t.f64(), longitude: t.f64() },
  (ctx, { name, description, latitude, longitude }) => {
    if (!name.trim() || name.length > 160 || !description.trim() || description.length > 3000 ||
        !Number.isFinite(latitude) || !Number.isFinite(longitude) || latitude < 32.45 || latitude > 33.3 || longitude < -97.65 || longitude > -96.25)
      throw new SenderError('Provide a title, description and coordinates within Greater Dallas.');
    const owned = [...ctx.db.residentReport.owner.filter(ctx.sender)];
    if (owned.filter(r => r.status === 'submitted').length >= 10 || owned.some(r => ctx.timestamp.microsSinceUnixEpoch - r.createdAt.microsSinceUnixEpoch < 30_000_000n))
      throw new SenderError('Please wait 30 seconds between reports; at most 10 open requests.');
    ctx.db.residentReport.insert({ id: 0n, owner: ctx.sender, name: name.trim(), description: description.trim(), latitude, longitude,
      status: 'submitted', createdAt: ctx.timestamp });
  });
export const withdrawReport = spacetimedb.reducer({ id: t.u64() }, (ctx, { id }) => {
  const report = ctx.db.residentReport.id.find(id);
  if (!report || !report.owner.equals(ctx.sender)) throw new SenderError('Not authorized');
  ctx.db.residentReport.id.update({ ...report, status: 'withdrawn' });
});
export const myReports = spacetimedb.view({ name: 'my_reports', public: true }, t.array(residentReport.rowType),
  ctx => [...ctx.db.residentReport.owner.filter(ctx.sender)]);
