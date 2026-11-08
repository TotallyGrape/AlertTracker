import { schema, table, t, Router, SyncResponse, SenderError } from 'spacetimedb/server';
import { ScheduleAt } from 'spacetimedb';
import type { ReducerCtx, InferSchema } from 'spacetimedb/server';
import { aggregateCommunity } from './community';

const reportExpiryTimer = table({ name: 'report_expiry_timer' }, {
  scheduledId: t.u64().primaryKey().autoInc(), scheduledAt: t.scheduleAt(),
});
const issueCard = table({ name: 'issue_card', public: true }, {
  id: t.string().primaryKey(), payloadJson: t.string(), expiresAt: t.string(),
});

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
  helpType: t.string().default('other'), peopleAffected: t.u32().default(1), locationText: t.string().default(''),
  aiStatus: t.string().default('not_requested'), aiSummary: t.string().default(''), aiUrgency: t.string().default(''),
  aiReasons: t.string().default(''), aiEvidence: t.string().default(''), aiModel: t.string().default(''),
  aiAttempts: t.u8().default(0), aiLeaseUntil: t.u64().default(0n), aiUpdatedAt: t.string().default(''),
});

// Private database configuration, read in procedures as `ctx.env.NAME`.
// Values are supplied when the module is published; they are never part of
// this source file or the built bundle. Every key is optional so the module
// can publish before all sign-ups are done: a procedure should check for
// `undefined` and mark that source as "missing key" in its health row.
//
// Never pass these values to clients, reducer arguments, logs, or table rows.
const spacetimedb = schema(
  { incident, sourceHealth, residentReport, reportExpiryTimer, issueCard },
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
const reportLifetime = 86_400_000_000n;
function expireResidentReports(ctx: ReducerCtx<InferSchema<typeof spacetimedb>>) {
  for (const card of ctx.db.issueCard.iter())
    if (Date.parse(card.expiresAt) <= Number(ctx.timestamp.microsSinceUnixEpoch/1000n)) ctx.db.issueCard.id.delete(card.id);
  for (const row of ctx.db.residentReport.iter()) {
    if (row.status === 'submitted' && row.createdAt.microsSinceUnixEpoch + reportLifetime <= ctx.timestamp.microsSinceUnixEpoch)
      ctx.db.residentReport.id.update({ ...row, status: 'expired', aiStatus: ['pending', 'processing'].includes(row.aiStatus) ? 'cancelled' : row.aiStatus });
  }
}
export const ensureReportExpiry = spacetimedb.reducer(ctx => {
  if (ctx.db.reportExpiryTimer.count() === 0n)
    ctx.db.reportExpiryTimer.insert({ scheduledId: 0n, scheduledAt: ScheduleAt.interval(60_000_000n) });
  expireResidentReports(ctx);
});
export const expireReports = spacetimedb.reducer({ onSchedule: reportExpiryTimer }, { timer: reportExpiryTimer.rowType }, ctx => expireResidentReports(ctx));
export const init = spacetimedb.init(ctx => {
  ctx.db.reportExpiryTimer.insert({ scheduledId: 0n, scheduledAt: ScheduleAt.interval(60_000_000n) });
});

// Read-only feed tables are written only through the credential-checked HTTP route.
const allowedSources = new Set(['nws_alerts', 'nws_weather', 'nwps', 'usgs_water', 'dallas_police', 'iem', 'nifc', 'earthquakes', 'fema_shelters', 'dallas_gis', 'openfreemap', 'overpass', 'dallas_311', 'eonet', 'tomtom', 'community_reports']);
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
export const claimResidentAi = spacetimedb.httpHandler((ctx, request) => {
  if (!ctx.env.INGEST_SECRET || !sameSecret(request.headers.get('x-ingest-secret') ?? '', ctx.env.INGEST_SECRET))
    return new SyncResponse('Unauthorized', { status: 401 });
  const jobs = ctx.withTx(tx => {
    const selected = [];
    for (const row of tx.db.residentReport.iter()) {
      if (selected.length >= 2) break;
      if (row.status === 'submitted' && row.createdAt.microsSinceUnixEpoch + reportLifetime <= tx.timestamp.microsSinceUnixEpoch) {
        tx.db.residentReport.id.update({ ...row, status: 'expired', aiStatus: ['pending', 'processing'].includes(row.aiStatus) ? 'cancelled' : row.aiStatus });
        continue;
      }
      if (row.status === 'submitted' && row.aiStatus === 'processing' && row.aiAttempts >= 3 && row.aiLeaseUntil < tx.timestamp.microsSinceUnixEpoch) {
        tx.db.residentReport.id.update({ ...row, aiStatus: 'failed' });
        continue;
      }
      if (row.status !== 'submitted' || row.aiAttempts >= 3 || !(row.aiStatus === 'pending' || row.aiStatus === 'processing' && row.aiLeaseUntil < tx.timestamp.microsSinceUnixEpoch)) continue;
      const lease = tx.timestamp.microsSinceUnixEpoch + 180_000_000n;
      tx.db.residentReport.id.update({ ...row, aiStatus: 'processing', aiAttempts: row.aiAttempts + 1, aiLeaseUntil: lease });
      // No owner identity, address or coordinates leave the database for AI processing.
      selected.push({ id: String(row.id), lease: String(lease), name: row.name, description: row.description,
        help_type: row.helpType, people_affected: row.peopleAffected });
    }
    return selected;
  });
  return new SyncResponse(JSON.stringify({ jobs }), { headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
});
export const finishResidentAi = spacetimedb.httpHandler((ctx, request) => {
  if (!ctx.env.INGEST_SECRET || !sameSecret(request.headers.get('x-ingest-secret') ?? '', ctx.env.INGEST_SECRET))
    return new SyncResponse('Unauthorized', { status: 401 });
  try {
    const text = request.text();
    if (text.length > 10000) throw new Error('Too large');
    const body = JSON.parse(text) as { id: string; lease: string; summary: string; urgency: string; reasons: string[]; evidence: string; model: string; failed?: boolean };
    if (!/^\d+$/.test(body.id) || !/^\d+$/.test(body.lease) || typeof body.model !== 'string' || body.model.length > 180) throw new Error('Invalid result');
    if (!body.failed && (typeof body.summary !== 'string' || !body.summary.trim() || body.summary.length > 600 ||
      !['low', 'medium', 'high', 'critical'].includes(body.urgency) || !Array.isArray(body.reasons) || body.reasons.length < 1 || body.reasons.length > 4 ||
      !body.reasons.every(reason => typeof reason === 'string' && reason.length > 0 && reason.length <= 200) || typeof body.evidence !== 'string' || body.evidence.length > 300)) throw new Error('Invalid assessment');
    const accepted = ctx.withTx(tx => {
      const row = tx.db.residentReport.id.find(BigInt(body.id));
      if (!row || row.status !== 'submitted' || row.aiStatus !== 'processing' || String(row.aiLeaseUntil) !== body.lease) return false;
      if (body.failed) {
        tx.db.residentReport.id.update({ ...row, aiStatus: row.aiAttempts < 3 ? 'pending' : 'failed' });
      } else {
        const original = (row.name + ' ' + row.description).toLowerCase();
        if (body.evidence && !original.includes(body.evidence.toLowerCase()) || ['high', 'critical'].includes(body.urgency) && body.evidence.trim().length < 5) throw new Error('Unsupported urgency');
        tx.db.residentReport.id.update({ ...row, aiStatus: 'complete', aiSummary: body.summary, aiUrgency: body.urgency,
          aiReasons: JSON.stringify(body.reasons), aiEvidence: body.evidence, aiModel: body.model, aiUpdatedAt: String(tx.timestamp.microsSinceUnixEpoch) });
      }
      return true;
    });
    return new SyncResponse(JSON.stringify({ accepted }), { status: accepted ? 200 : 409, headers: { 'content-type': 'application/json' } });
  } catch { return new SyncResponse('Invalid assessment', { status: 400 }); }
});
export const ingestIssues = spacetimedb.httpHandler((ctx, request) => {
  if (!ctx.env.INGEST_SECRET || !sameSecret(request.headers.get('x-ingest-secret') ?? '', ctx.env.INGEST_SECRET))
    return new SyncResponse('Unauthorized', { status: 401 });
  try {
    const text=request.text();
    if (text.length>12_000_000) throw new Error('Too large');
    const body=JSON.parse(text) as { cards: Array<{ id: string; level: string; ai_status: string; expires_at: string; [key:string]:unknown }> };
    if (!Array.isArray(body.cards) || body.cards.length>5000) throw new Error('Invalid cards');
    const ids=new Set<string>();
    for (const card of body.cards) {
      if (typeof card.id!=='string' || !card.id.startsWith('issue:') || ids.has(card.id) ||
          !['informational','caution','active_threat','critical'].includes(card.level) || !['pending','rejected','complete'].includes(card.ai_status) ||
          !Number.isFinite(Date.parse(card.expires_at)) || Date.parse(card.expires_at)<=Number(ctx.timestamp.microsSinceUnixEpoch/1000n)) throw new Error('Invalid card');
      ids.add(card.id);
    }
    ctx.withTx(tx=>{
      for (const old of tx.db.issueCard.iter()) if (!ids.has(old.id)) tx.db.issueCard.id.delete(old.id);
      for (const card of body.cards) {
        const row={ id:card.id, payloadJson:JSON.stringify(card), expiresAt:card.expires_at };
        if (tx.db.issueCard.id.find(card.id)) tx.db.issueCard.id.update(row); else tx.db.issueCard.insert(row);
      }
    });
    return new SyncResponse('{"accepted":true}', { headers:{'content-type':'application/json'} });
  } catch { return new SyncResponse('Invalid issue snapshot', { status:400 }); }
});
export const communitySignals = spacetimedb.httpHandler((ctx, request) => {
  if (!ctx.env.INGEST_SECRET || !sameSecret(request.headers.get('x-ingest-secret') ?? '', ctx.env.INGEST_SECRET))
    return new SyncResponse('Unauthorized', { status: 401 });
  const clusters=ctx.withTx(tx=>aggregateCommunity(tx.db.residentReport.iter(),tx.timestamp.microsSinceUnixEpoch));
  return new SyncResponse(JSON.stringify({ clusters }),{ headers:{ 'content-type':'application/json', 'cache-control':'no-store' } });
});
export const routes = spacetimedb.httpRouter(new Router().post('/ingest', ingest).post('/resident-ai/claim', claimResidentAi).post('/resident-ai/result', finishResidentAi).post('/issues', ingestIssues).post('/community-signals', communitySignals));

export const submitReport = spacetimedb.reducer({ name: t.string(), description: t.string(), latitude: t.f64(), longitude: t.f64() },
  (ctx, { name, description, latitude, longitude }) => {
    expireResidentReports(ctx);
    if (!name.trim() || name.length > 160 || !description.trim() || description.length > 3000 ||
        !Number.isFinite(latitude) || !Number.isFinite(longitude) || latitude < 32.45 || latitude > 33.3 || longitude < -97.65 || longitude > -96.25)
      throw new SenderError('Provide a title, description and coordinates within Greater Dallas.');
    const owned = [...ctx.db.residentReport.owner.filter(ctx.sender)];
    if (owned.filter(r => r.status === 'submitted').length >= 10 || owned.some(r => ctx.timestamp.microsSinceUnixEpoch - r.createdAt.microsSinceUnixEpoch < 30_000_000n))
      throw new SenderError('Please wait 30 seconds between reports; at most 10 open requests.');
    ctx.db.residentReport.insert({ id: 0n, owner: ctx.sender, name: name.trim(), description: description.trim(), latitude, longitude,
      status: 'submitted', createdAt: ctx.timestamp, helpType: 'other', peopleAffected: 1, locationText: '', aiStatus: 'not_requested',
      aiSummary: '', aiUrgency: '', aiReasons: '', aiEvidence: '', aiModel: '', aiAttempts: 0, aiLeaseUntil: 0n, aiUpdatedAt: '' });
  });
export const submitAssistanceRequest = spacetimedb.reducer({ name: t.string(), description: t.string(), latitude: t.f64(), longitude: t.f64(),
  helpType: t.string(), peopleAffected: t.u32(), locationText: t.string() }, (ctx, args) => {
  if (!['evacuation', 'medical', 'shelter', 'food_water', 'transport', 'accessibility', 'welfare', 'other'].includes(args.helpType) ||
      args.peopleAffected < 1 || args.peopleAffected > 1000 || !args.locationText.trim() || args.locationText.length > 300)
    throw new SenderError('Select a help type, enter 1–1000 people, and provide an address or landmark.');
  submitReport(ctx, args);
  const row = [...ctx.db.residentReport.owner.filter(ctx.sender)].find(r => r.createdAt.microsSinceUnixEpoch === ctx.timestamp.microsSinceUnixEpoch && r.aiStatus === 'not_requested' && r.status === 'submitted');
  if (!row) throw new SenderError('Unable to save request');
  ctx.db.residentReport.id.update({ ...row, helpType: args.helpType, peopleAffected: args.peopleAffected, locationText: args.locationText.trim(), aiStatus: 'pending' });
});
export const withdrawReport = spacetimedb.reducer({ id: t.u64() }, (ctx, { id }) => {
  const report = ctx.db.residentReport.id.find(id);
  if (!report || !report.owner.equals(ctx.sender)) throw new SenderError('Not authorized');
  ctx.db.residentReport.id.update({ ...report, status: 'withdrawn', aiStatus: ['pending', 'processing'].includes(report.aiStatus) ? 'cancelled' : report.aiStatus });
});
export const myReports = spacetimedb.view({ name: 'my_reports', public: true }, t.array(residentReport.rowType),
  ctx => [...ctx.db.residentReport.owner.filter(ctx.sender)]);
