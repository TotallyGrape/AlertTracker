import { useEffect, useMemo, useRef, useState } from 'react';
import { useSpacetimeDB, useTable } from 'spacetimedb/react';
import type { FeatureCollection } from 'geojson';
import { tables } from '../module_bindings';
import { DallasMap } from './DallasMap';
import { residentPins } from '../residentPins';

const activeIncidents = tables.incident.where(row => row.active.eq(true));

// Approximate the requested Dallas-centered circle, independent of map zoom/panning.
function inDallasContextArea(row: { latitude?: number; longitude?: number }) {
  if (row.latitude === undefined || row.longitude === undefined) return false;
  const radians = Math.PI / 180;
  const lat = 32.8 * radians;
  const deltaLat = (row.latitude - 32.8) * radians;
  const deltaLon = (row.longitude + 96.8) * radians;
  const a = Math.sin(deltaLat / 2) ** 2 + Math.cos(lat) * Math.cos(row.latitude * radians) * Math.sin(deltaLon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a))) <= 32;
}

type Details = Record<string, any>;
const num = (value: unknown) => typeof value === 'number' ? value : typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : null;

// Short source-specific facts for the popup, built only from fields the provider supplied.
function factsFor(source: string, details: Details): string {
  const a: Details = details.attributes ?? {};
  const parts: string[] = [];
  if (source === 'earthquakes') {
    if (num(a.magnitude) !== null) parts.push(`Magnitude ${num(a.magnitude)!.toFixed(1)}`);
    if (num(a.depth_km) !== null) parts.push(`depth ${num(a.depth_km)!.toFixed(1)} km`);
  } else if (source === 'iem') {
    if (num(a.magnitude) !== null && num(a.magnitude) !== 0) parts.push(`${num(a.magnitude)} ${a.unit ?? ''}`.trim());
    if (a.city) parts.push(`${a.city}${a.county ? `, ${a.county} County` : ''}`);
    if (a.source) parts.push(`reported by ${String(a.source).toLowerCase()}`);
  } else if (source === 'nifc') {
    if (num(a.poly_GISAcres) !== null) parts.push(`${Math.round(num(a.poly_GISAcres)!).toLocaleString()} acres`);
    if (num(a.attr_PercentContained) !== null) parts.push(`${num(a.attr_PercentContained)}% contained`);
  } else if (source === 'nws_alerts') {
    for (const key of ['severity', 'urgency', 'certainty']) if (a[key] && a[key] !== 'Unknown') parts.push(`${key[0].toUpperCase()}${key.slice(1)}: ${a[key]}`);
  } else if (source === 'dallas_police') {
    if (a.priority) parts.push(`Priority ${a.priority}`);
    if (details.location_accuracy === 'geocoded_block') parts.push('approximate block-level location');
    if (details.location_accuracy === 'geocoded_intersection') parts.push('approximate intersection location');
  } else if (source === 'fema_shelters') {
    if (a.shelter_status) parts.push(`Status: ${a.shelter_status}`);
    if (num(a.evacuation_capacity) !== null) parts.push(`capacity ${num(a.evacuation_capacity)}`);
  }
  return parts.join(' · ');
}

// Returns the previous array when the same rows (by key) come back, so downstream memos and the map's
// setData only run when something actually changed. Without this the map re-uploaded every record each render.
function useStableRows<T>(rows: T[], key: (row: T) => string): T[] {
  const cache = useRef<{ signature: string; rows: T[] }>({ signature: '', rows });
  const signature = rows.map(key).join('\n');
  if (signature !== cache.current.signature) cache.current = { signature, rows };
  return cache.current.rows;
}
const rowKey = (row: { id: string; fetchedAt: { microsSinceUnixEpoch: bigint } }) => `${row.id}@${row.fetchedAt.microsSinceUnixEpoch}`;

export function LiveMap() {
  const { isActive } = useSpacetimeDB();
  const [incidents, ready] = useTable(activeIncidents);
  const [sources, sourcesReady] = useTable(tables.sourceHealth);
  const [ownReports] = useTable(tables.myReports);
  const [showRequests, setShowRequests] = useState(true);
  const [resources, setResources] = useState(false);
  const [observations, setObservations] = useState(false);
  const [alerts, setAlerts] = useState(true);
  const [clock, setClock] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 30000); return () => clearInterval(timer); }, []);
  // Keyed by the sorted names so the 30-second clock tick only matters when the stale set really changes.
  const staleKey = useMemo(() => sources.filter(s => s.stale || !s.lastSuccess || clock - Date.parse(s.lastSuccess) > s.intervalSeconds * 2000 || clock - Number(s.syncedAt.microsSinceUnixEpoch / 1000n) > 120000).map(s => s.source).sort().join(','), [sources, clock]);
  const staleSources = useMemo(() => new Set(staleKey ? staleKey.split(',') : []), [staleKey]);
  const current = useStableRows(useMemo(() => incidents.filter(row => {
    try {
      const details = JSON.parse(row.detailsJson);
      if (details.expires_at && Date.parse(details.expires_at) <= clock) return false;
      const hours = ['nwps', 'usgs_water'].includes(row.source) ? 6 : ['iem', 'earthquakes'].includes(row.source) ? 24 : null;
      return !hours || details.observed_at && clock - Date.parse(details.observed_at) <= hours * 3600000;
    } catch { return false; }
  }), [incidents, clock]), rowKey);
  const { routine, facilities, events, locatedEvents } = useMemo(() => {
    const events = current.filter(row => ['warning', 'incident'].includes(row.kind));
    return { routine: current.filter(row => ['observation', 'forecast'].includes(row.kind) && inDallasContextArea(row)),
      facilities: current.filter(row => row.kind === 'resource' && inDallasContextArea(row)),
      events, locatedEvents: events.filter(row => row.latitude !== undefined) };
  }, [current]);
  const visible = useMemo(() => current.filter(row => row.kind === 'resource' ? resources && inDallasContextArea(row) : ['observation', 'forecast'].includes(row.kind) ? observations && inDallasContextArea(row) : ['warning', 'incident'].includes(row.kind) && alerts), [current, resources, observations, alerts]);
  const requestPins = useStableRows(useMemo(() => residentPins(ownReports, clock, isActive), [ownReports, clock, isActive]), row => JSON.stringify(row));
  const feedFeatures = useMemo<FeatureCollection>(() => ({ type: 'FeatureCollection', features: visible.flatMap(row => {
    if (row.latitude === undefined || row.longitude === undefined) return [];
    let details: Details = {};
    try { details = JSON.parse(row.detailsJson); } catch { /* keep the basic popup */ }
    const ai = details.ai && typeof details.ai.headline === 'string' ? details.ai : null;
    const properties = { name: row.name, description: row.description, kind: row.kind, source: row.source,
      stale: !isActive || staleSources.has(row.source), category: row.category,
      facts: factsFor(row.source, details), instruction: typeof details.attributes?.instruction === 'string' ? details.attributes.instruction : '',
      observedAt: details.observed_at ?? '', updatedAt: details.updated_at ?? '', expiresAt: details.expires_at ?? '',
      fetchedAt: new Date(Number(row.fetchedAt.microsSinceUnixEpoch / 1000n)).toISOString(),
      aiHeadline: ai?.headline ?? '', aiSummary: ai?.summary ?? '',
      priority: typeof details.priority?.score === 'number' ? details.priority.score : 0,
      priorityLabel: details.priority?.label ?? '',
      priorityReasons: Array.isArray(details.priority?.reasons) ? details.priority.reasons.join('\n') : '',
      priorityBasis: typeof details.priority?.basis === 'string' ? details.priority.basis : '',
      priorityRulesScore: typeof details.priority?.rules_score === 'number' ? details.priority.rules_score : 0,
      priorityFactor: details.priority?.critical_factor ?? '', priorityEvidence: details.priority?.evidence ?? '' };
    const result: FeatureCollection['features'] = [{ type: 'Feature', id: row.id, geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] }, properties }];
    try {
      const geometry = JSON.parse(row.geometryJson);
      if (geometry && ['Polygon', 'MultiPolygon'].includes(geometry.type)) result.push({ type: 'Feature', id: row.id + ':area', geometry, properties });
    } catch { /* Invalid geometry is omitted, its label point can still display. */ }
    return result;
  }) }), [visible, staleSources, isActive]);
  const features = useMemo<FeatureCollection>(() => ({ type: 'FeatureCollection', features: [...feedFeatures.features, ...(showRequests ? requestPins : [])] }), [feedFeatures, requestPins, showRequests]);
  return <>
    <div className="live-toolbar" aria-label="Map layers">
      <label className="glass-chip"><input type="checkbox" checked={showRequests} onChange={e => setShowRequests(e.target.checked)} /> Your active requests ({requestPins.length})</label>
      <label className="glass-chip layer-alerts"><input type="checkbox" checked={alerts} onChange={e => setAlerts(e.target.checked)} /> Alerts & reported incidents ({locatedEvents.length} mapped)</label>
      <label className="glass-chip layer-routine"><input type="checkbox" checked={observations} onChange={e => setObservations(e.target.checked)} /> Routine readings & forecasts ({routine.length})</label>
      <label className="glass-chip layer-facilities"><input type="checkbox" checked={resources} onChange={e => setResources(e.target.checked)} /> Facilities ({facilities.length})</label>
    </div>
    <p className="map-data-note">Readings and facilities cover approximately 20 miles around Dallas. Alerts and incidents retain regional coverage.</p>
    <p className="map-data-summary" role="status">{!isActive ? 'Disconnected — displayed data may be stale.' : !ready || !sourcesReady ? 'Loading shared data…' : `${visible.filter(r => r.latitude !== undefined).length + (showRequests ? requestPins.length : 0)} pins shown · ${current.filter(r => r.kind === 'warning').length} alerts · ${events.filter(r => r.latitude === undefined).length} reported incidents without coordinates.`} Your requests are purple, visible only to you, and leave the map after 24 hours or withdrawal.</p>
    {isActive && ready && sourcesReady && alerts && locatedEvents.length === 0 && <p className="map-data-note">No located alerts or reported incidents in the current feeds. Routine measurements are separate and do not establish danger. Coverage is incomplete.</p>}
    <DallasMap features={features} />
    <details className="feed-health glass--subtle"><summary>Feed status · {staleSources.size} stale or unavailable · {sources.length}/12 reporting</summary>
      <p>Red: official alerts · Orange: reported incidents · Blue: routine readings/forecasts · Green: unverified facilities · Gray: stale. A reading is not a warning; a reported incident is not necessarily a confirmed danger.</p>
      <ul>{sources.map(source => <li key={source.source}>{source.source.replace(/_/g, ' ')}: {staleSources.has(source.source) ? 'stale / unavailable' : source.status}{source.error ? ` — ${source.error}` : ''}</li>)}</ul>
    </details>
  </>;
}
