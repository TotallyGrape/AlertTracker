import { useEffect, useRef, useState } from 'react';
import { FullscreenControl, Map, NavigationControl, ScaleControl, setWorkerUrl, Popup, type GeoJSONSource, type ExpressionSpecification } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';

setWorkerUrl(workerUrl);

// Regional viewing extent for DFW, not an administrative boundary or navigation limit.
const greaterDallasBounds: [[number, number], [number, number]] = [
  [-97.65, 32.45],
  [-96.25, 33.3],
];

const emptyFeatures: FeatureCollection = { type: 'FeatureCollection', features: [] };

// "12 min ago (3:45 PM)" in Dallas time; empty when the value is missing or invalid.
function when(iso: unknown): string {
  const time = typeof iso === 'string' && iso ? Date.parse(iso) : NaN;
  if (!Number.isFinite(time)) return '';
  const minutes = Math.round((Date.now() - time) / 60000);
  const relative = Math.abs(minutes) < 1 ? 'just now' : minutes > 0
    ? minutes < 60 ? `${minutes} min ago` : minutes < 2880 ? `${Math.round(minutes / 60)} h ago` : `${Math.round(minutes / 1440)} days ago`
    : -minutes < 60 ? `in ${-minutes} min` : -minutes < 2880 ? `in ${Math.round(-minutes / 60)} h` : `in ${Math.round(-minutes / 1440)} days`;
  const clock = new Date(time).toLocaleString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  return `${relative} (${clock})`;
}

const sourceNote: Record<string, string> = {
  earthquakes: 'Measured by USGS instruments — shaking and damage are not reported here.',
  iem: 'Preliminary storm report — may be revised.',
  nifc: 'Published fire perimeter — current conditions must be verified.',
  dallas_police: 'Reported incident — current danger is not independently confirmed.',
};

function popupContent(p: Record<string, any>): HTMLElement {
  const add = (parent: HTMLElement, tag: string, text: string, className?: string) => {
    const element = document.createElement(tag); element.textContent = text;
    if (className) element.className = className;
    parent.append(element); return element;
  };
  const content = document.createElement('div'); content.className = 'pin-popup';
  const priority = Number(p.priority) || 0;
  if (priority > 0) {
    const level = priority >= 9 ? 'critical' : priority >= 7 ? 'high' : priority >= 5 ? 'elevated' : priority >= 3 ? 'moderate' : 'low';
    add(content, 'span', `Priority ${priority}/10 · ${p.priorityLabel || level}`, `pin-priority pin-priority-${level}`);
  }
  add(content, 'strong', p.aiHeadline || p.name || 'Incident');
  if (p.aiHeadline && p.aiHeadline !== p.name) add(content, 'small', `Source label: ${p.name}`, 'pin-code');
  add(content, 'p', sourceNote[p.source] ?? (p.kind === 'warning' ? 'Official alert — consult the source for severity and instructions.'
    : p.kind === 'incident' ? 'Reported incident — current danger is not independently confirmed.'
    : p.kind === 'resource' ? 'Facility — availability unverified.' : 'Routine reading / forecast — not a danger alert.'), 'pin-note');
  if (p.facts) add(content, 'p', p.facts, 'pin-facts');
  const happened = when(p.observedAt), updated = when(p.updatedAt), expires = when(p.expiresAt);
  const times = [happened && `Happened ${happened}`, !happened && updated && `Updated ${updated}`, expires && `Expires ${expires}`].filter(Boolean).join(' · ');
  add(content, 'p', times || `No event time from source · received ${when(p.fetchedAt) || 'time unknown'}`, 'pin-time');
  if (p.aiSummary) {
    const box = document.createElement('div'); box.className = 'pin-ai';
    add(box, 'small', 'AI summary · may contain errors');
    add(box, 'p', p.aiSummary);
    content.append(box);
  }
  if (p.instruction) add(content, 'p', `Official instructions: ${p.instruction}`, 'pin-instruction');
  if (p.description) {
    if (p.aiHeadline) {
      const original = document.createElement('details');
      add(original, 'summary', 'Original text');
      add(original, 'p', p.description);
      content.append(original);
    } else add(content, 'p', p.description);
  }
  const byAI = String(p.priorityBasis || '').startsWith('nemotron');
  if (byAI && p.priorityFactor) add(content, 'p', `AI raised priority: ${p.priorityFactor}${p.priorityEvidence ? ` — “${p.priorityEvidence}”` : ''}`, 'pin-raised');
  if (priority > 0 && p.priorityReasons) {
    const why = document.createElement('details');
    add(why, 'summary', 'Why this priority');
    const list = document.createElement('ul');
    for (const reason of String(p.priorityReasons).split('\n')) add(list, 'li', reason);
    why.append(list);
    add(why, 'small', byAI
      ? `Assessed by Nemotron AI (rules score ${p.priorityRulesScore}/10). AI may make mistakes. A low score does not mean an area is safe.`
      : 'Rule-based triage score from the source data. A low score does not mean an area is safe.');
    content.append(why);
  }
  add(content, 'small', `${p.source ?? ''}${p.stale ? ' · stale' : ''}`, 'pin-source');
  return content;
}
export function DallasMap({ features = emptyFeatures }: { features?: FeatureCollection }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const dataRef = useRef(features);
  dataRef.current = features;
  useEffect(() => {
    (mapRef.current?.getSource('live-incidents') as GeoJSONSource | undefined)?.setData(features);
  }, [features]);

  useEffect(() => {
    if (!container.current) return;
    setStatus('loading');
    let map: Map;
    let loaded = false;
    try {
      map = new Map({
        container: container.current,
        style: 'https://tiles.openfreemap.org/styles/liberty',
        bounds: greaterDallasBounds,
        fitBoundsOptions: { padding: 28 },
        canvasContextAttributes: { antialias: true },
        attributionControl: { compact: true },
      });
    } catch {
      setStatus('error');
      return;
    }
    mapRef.current = map;
    map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');
    map.addControl(new FullscreenControl(), 'top-right');
    map.addControl(new ScaleControl({ unit: 'imperial' }), 'bottom-left');
    map.on('load', () => {
      map.addSource('dallas-city-limits', {
        type: 'geojson',
        data: `${import.meta.env.BASE_URL}data/dallas-city-limits.geojson`,
        attribution: 'City of Dallas GIS Services',
      });
      // Place the boundary under labels so road and neighborhood names stay readable.
      const labelLayer = map.getStyle().layers.find(layer => layer.type === 'symbol')?.id;
      map.addLayer({
        id: 'dallas-city-fill', type: 'fill', source: 'dallas-city-limits',
        paint: { 'fill-color': '#326c5b', 'fill-opacity': 0.035 },
      }, labelLayer);
      map.addLayer({
        id: 'dallas-city-border-halo', type: 'line', source: 'dallas-city-limits',
        paint: { 'line-color': '#ffffff', 'line-width': 4, 'line-opacity': 0.8 },
      }, labelLayer);
      map.addLayer({
        id: 'dallas-city-border', type: 'line', source: 'dallas-city-limits',
        paint: { 'line-color': '#326c5b', 'line-width': 1.8, 'line-opacity': 0.85 },
      }, labelLayer);
      map.addSource('live-incidents', { type: 'geojson', data: dataRef.current });
      const color: ExpressionSpecification = ['case', ['==', ['get', 'stale'], true], '#858585', ['==', ['get', 'kind'], 'resource'], '#326c5b', ['in', ['get', 'kind'], ['literal', ['observation', 'forecast']]], '#2874a6', ['==', ['get', 'kind'], 'warning'], '#c44635', '#c47a22'];
      map.addLayer({ id: 'incident-areas', type: 'fill', source: 'live-incidents', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': [...color], 'fill-opacity': 0.16 } }, labelLayer);
      map.addLayer({ id: 'incident-outlines', type: 'line', source: 'live-incidents', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'line-color': [...color], 'line-width': 1.5 } }, labelLayer);
      map.addLayer({ id: 'incident-pins', type: 'circle', source: 'live-incidents', filter: ['==', ['geometry-type'], 'Point'], // Higher-priority pins are larger and drawn on top; unscored pins keep their old sizes.
        layout: { 'circle-sort-key': ['coalesce', ['get', 'priority'], 0] },
        paint: { 'circle-color': [...color], 'circle-radius': ['case', ['in', ['get', 'kind'], ['literal', ['observation', 'forecast']]], 3.5,
          ['>', ['coalesce', ['get', 'priority'], 0], 0], ['interpolate', ['linear'], ['get', 'priority'], 1, 4, 10, 10], 5.5],
          'circle-stroke-color': ['case', ['>=', ['coalesce', ['get', 'priority'], 0], 9], '#5c0b0b', '#fff'],
          'circle-stroke-width': ['case', ['>=', ['coalesce', ['get', 'priority'], 0], 9], 2.5, 1.5] } });
      map.on('click', 'incident-pins', event => {
        const feature = event.features?.[0];
        if (!feature || feature.geometry.type !== 'Point') return;
        new Popup({ maxWidth: '340px' }).setLngLat(feature.geometry.coordinates as [number, number]).setDOMContent(popupContent(feature.properties ?? {})).addTo(map);
      });
      map.on('mouseenter', 'incident-pins', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'incident-pins', () => { map.getCanvas().style.cursor = ''; });
      loaded = true;
      setStatus('ready');
    });
    map.on('error', () => setStatus('error'));
    map.on('idle', () => { if (loaded) setStatus('ready'); });
    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(container.current);
    return () => {
      resizeObserver.disconnect();
      mapRef.current = null;
      map.remove();
    };
  }, [attempt]);

  return (
    <section className="map-panel" aria-label="Explore Greater Dallas">
      <div className="map-heading">
        <div><h2>Explore Greater Dallas</h2><p>Dallas–Fort Worth and surrounding communities</p></div>
        <button className="map-reset" type="button" onClick={() => mapRef.current?.fitBounds(greaterDallasBounds, { padding: 28, bearing: 0, pitch: 0, duration: 700 })}>Back to DFW <span aria-hidden="true">↗</span></button>
      </div>
      <div className="map-frame">
        <div ref={container} className="dallas-map" />
        {status === 'loading' && <div className="map-message" role="status">Loading map…</div>}
        {status === 'error' && <div className="map-message map-error" role="status">Some map content could not load. Check your connection.<button type="button" onClick={() => setAttempt(value => value + 1)}>Reload map</button></div>}
      </div>
      <div className="map-caption"><span>Drag to explore · Scroll or pinch to zoom</span><span className="boundary-legend"><i aria-hidden="true" /> Dallas city limits</span></div>
    </section>
  );
}
