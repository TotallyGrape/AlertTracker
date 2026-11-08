"""Independent, cached public disaster-feed API. Run from backend with uvicorn app.main:app."""
import asyncio
import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import box, mapping, shape
from .spacetime_sync import run as run_sync, state as sync_state
from . import nemotron
from . import resident_ai
from . import issues
from .water_risk import enrich_water
from .priority import enrich_priority
from .extra_feeds import collect_311, collect_eonet
from .tomtom import collect_tomtom
from .community import collect_community

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
BBOX = tuple(float(x) for x in os.getenv('BBOX', '-97.65,32.45,-96.25,33.3').split(','))
if len(BBOX) != 4 or not (-180 <= BBOX[0] < BBOX[2] <= 180 and -90 <= BBOX[1] < BBOX[3] <= 90):
    raise ValueError('BBOX must be west,south,east,north')
REGION = box(*BBOX)
CACHE = ROOT / '.cache'
STYLE = 'https://tiles.openfreemap.org/styles/liberty'
INTERVALS = {'nws_alerts': 60, 'nws_weather': 900, 'nwps': 300, 'usgs_water': 300,
             'dallas_police': 120, 'iem': 300, 'nifc': 600, 'earthquakes': 60,
             'fema_shelters': 1200, 'dallas_gis': 86400, 'openfreemap': 86400, 'overpass': 86400,
             'dallas_311': 3600, 'eonet': 1800, 'tomtom': max(300, int(os.getenv('TOMTOM_POLL_SECONDS', '900'))), 'community_reports':60}
ENABLED = os.getenv('ENABLED_SOURCES', ','.join(INTERVALS)).split(',')
if any(s not in INTERVALS for s in ENABLED):
    raise ValueError('Unknown ENABLED_SOURCES entry')
snapshots = {}
health = {s: {'status': 'pending', 'last_success': None, 'last_attempt': None, 'error': None} for s in ENABLED}
# Police calls publish street text, not coordinates. The City of Dallas street locator (the same one the
# city's own active-calls page uses) turns "block + street" or "street / street" into a point.
GEOCODER = 'https://gis.dallascityhall.com/arcgis/rest/services/Crm_public/CrmDallasStreetsLocator/GeocodeServer/findAddressCandidates'
GEOCODE_MIN_SCORE = 90
GEOCODE_TYPES = {'StreetAddress': 'geocoded_block', 'StreetInt': 'geocoded_intersection'}
GEOCODE_RETRY_MISS = timedelta(hours=24)
GEOCODE_MAX_NEW = 60  # new lookups per refresh; the rest wait for the next poll
GEOCODE_CACHE_LIMIT = 20000
GEOCODE_FILE = 'police_geocodes.json'
geocodes = {}  # normalized address -> result, persisted beside the snapshots
logger = logging.getLogger('disaster_api')


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    if value is None or value == '':
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc).isoformat() if result.tzinfo is None else result.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def category(text):
    text = text.lower()
    for words, name in [('flood|water', 'flood'), ('tornado', 'tornado'), ('fire|smoke', 'wildfire'),
                        ('earthquake', 'earthquake'), ('heat', 'heat'), ('winter|snow|ice|freeze', 'winter_weather'),
                        ('wind|wnd|gust|storm|tstm|hail|lightning', 'severe_weather')]:
        if any(word in text for word in words.split('|')):
            return name
    return 'other'


def record(source, identifier, name, description, geometry=None, *, kind='incident', event_category=None,
           updated_at=None, observed_at=None, expires_at=None, source_url=None, attributes=None):
    """Keep authentic geometry; representative point is a label, never an estimated impact radius."""
    item = {'id': f'{source}:{identifier}', 'source': source, 'name': str(name), 'description': str(description or ''),
            'kind': kind, 'category': event_category or category(str(name)), 'updated_at': stamp(updated_at),
            'observed_at': stamp(observed_at), 'expires_at': stamp(expires_at), 'source_url': source_url,
            'attributes': attributes or {}}
    if not geometry:
        return {**item, 'latitude': None, 'longitude': None, 'geometry': None, 'location_accuracy': 'unknown'}
    geom = shape(geometry)
    if geom.is_empty or not geom.is_valid:
        raise ValueError('Invalid upstream geometry')
    if not geom.intersects(REGION):
        return None
    point = geom.intersection(REGION).representative_point()
    if not (-180 <= point.x <= 180 and -90 <= point.y <= 90):
        raise ValueError('Invalid coordinates')
    return {**item, 'latitude': point.y, 'longitude': point.x, 'geometry': mapping(geom),
            'location_accuracy': 'source_point' if geom.geom_type == 'Point' else 'representative_point'}


def point(lon, lat):
    return {'type': 'Point', 'coordinates': [float(lon), float(lat)]}


def recent(value, hours=24):
    parsed = stamp(value)
    return parsed is not None and now() - timedelta(hours=hours) <= datetime.fromisoformat(parsed) <= now() + timedelta(minutes=10)


async def get(client, url, **params):
    response = await client.get(url, params=params or None)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get('error'):
        raise ValueError(str(data['error'])[:300])
    return data


def police_address(p):
    """Build a locator query from a police row, or None when it is too vague to place."""
    location = ' '.join(str(p.get('location') or '').split())
    if not location:
        return None
    if '/' in location:
        streets = [part.strip() for part in location.split('/') if part.strip()]
        return ' & '.join(streets) if len(streets) == 2 else None
    block = str(p.get('block') or '').strip()
    # A street name alone would match the whole street, which is not a usable location.
    return f'{block} {location}' if block.isdigit() else None


async def geocode(client, address, budget):
    """Cached lookup. Returns a hit, a recorded miss, or None when not looked up (budget or transient error)."""
    key = address.upper()
    cached = geocodes.get(key)
    if cached and (cached['lon'] is not None or now() - datetime.fromisoformat(cached['checked_at']) < GEOCODE_RETRY_MISS):
        return cached
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    try:
        data = await get(client, GEOCODER, **{'Single Line Input': address, 'outFields': 'Addr_type',
                                              'maxLocations': 1, 'outSR': 4326, 'f': 'json'})
    except (httpx.HTTPError, ValueError):
        return None  # Transient: try again next poll instead of caching a false miss.
    candidates = data.get('candidates') if isinstance(data, dict) else None
    best = candidates[0] if candidates else None
    result = {'checked_at': now().isoformat(), 'lon': None, 'lat': None}
    try:
        if best and best['score'] >= GEOCODE_MIN_SCORE and best['attributes'].get('Addr_type') in GEOCODE_TYPES:
            result.update(lon=float(best['location']['x']), lat=float(best['location']['y']), match=best['address'],
                          score=best['score'], accuracy=GEOCODE_TYPES[best['attributes']['Addr_type']])
    except (KeyError, TypeError, ValueError):
        pass
    geocodes[key] = result
    return result


def save_geocodes():
    if len(geocodes) > GEOCODE_CACHE_LIMIT:
        for key in sorted(geocodes, key=lambda k: geocodes[k]['checked_at'])[:len(geocodes) - GEOCODE_CACHE_LIMIT]:
            del geocodes[key]
    CACHE.mkdir(exist_ok=True)
    target = CACHE / GEOCODE_FILE
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(geocodes), encoding='utf-8')
    temporary.replace(target)


async def arcgis(client, url):
    features = []
    for offset in range(0, 10000, 1000):
        data = await get(client, url, where='1=1', geometry=','.join(map(str, BBOX)),
                         geometryType='esriGeometryEnvelope', inSR=4326, outSR=4326,
                         spatialRel='esriSpatialRelIntersects', outFields='*', f='geojson',
                         resultRecordCount=1000, resultOffset=offset)
        page = data['features']
        features.extend(page)
        if len(page) < 1000 and not data.get('exceededTransferLimit'):
            return features
    raise ValueError('ArcGIS pagination limit exceeded; snapshot not replaced')


async def collect(source, client):
    items, boundaries = [], []
    def add(*args, **kwargs):
        item = record(source, *args, **kwargs)
        if item:
            items.append(item)

    if source == 'community_reports':
        items = await collect_community(client, record, now())
    elif source == 'tomtom':
        items = await collect_tomtom(client, BBOX, record, now())
    elif source == 'dallas_311':
        items = await collect_311(client, BBOX, record, now())
    elif source == 'eonet':
        items = await collect_eonet(client, BBOX, record, now())
    elif source == 'nws_alerts':
        data = await get(client, 'https://api.weather.gov/alerts/active', area='TX')
        zones = {}
        for f in data['features']:
            p = f['properties']
            geometry = f.get('geometry')
            if not geometry:
                geometries = []
                for url in p.get('affectedZones', []):
                    if not url.startswith('https://api.weather.gov/zones/'):
                        continue
                    if url not in zones:
                        zones[url] = (await get(client, url)).get('geometry')
                    if zones[url]:
                        geometries.append(shape(zones[url]))
                if geometries:
                    from shapely.ops import unary_union
                    geometry = mapping(unary_union(geometries))
            add(p.get('id', f.get('id')), p['event'], p.get('description'), geometry,
                kind='warning', updated_at=p.get('sent'), expires_at=p.get('expires'), source_url=p.get('id'),
                attributes={k: p.get(k) for k in ['severity', 'urgency', 'certainty', 'instruction', 'areaDesc']})
    elif source == 'nws_weather':
        data = await get(client, 'https://api.weather.gov/points/32.7767,-96.7970')
        url = data['properties']['forecast']
        forecast = await get(client, url)
        p = forecast['properties']
        if p.get('periods'):
            period = p['periods'][0]
            add('dallas-forecast', f"Dallas forecast: {period['shortForecast']}", period.get('detailedForecast'),
                forecast.get('geometry'), kind='forecast', event_category='weather', updated_at=p.get('updateTime'),
                expires_at=period.get('endTime'), source_url=url, attributes={'periods': p['periods']})
    elif source == 'nwps':
        for gauge in os.getenv('NWPS_GAUGES', 'dalt2').split(','):
            url = f'https://api.water.noaa.gov/nwps/v1/gauges/{gauge.strip()}'
            p = await get(client, url)
            observed = p.get('status', {}).get('observed', {})
            if recent(observed.get('validTime'), 6):
                add(gauge, p['name'], f"River observation: {observed.get('primary')} {observed.get('primaryUnit')}; {observed.get('floodCategory')}",
                    point(p['longitude'], p['latitude']), kind='observation', event_category='river',
                    observed_at=observed.get('validTime'), source_url=url,
                    attributes={'observed': observed, 'flood_thresholds': p.get('flood', {})})
    elif source == 'usgs_water':
        url = 'https://api.waterdata.usgs.gov/ogcapi/v1/collections/latest-continuous/items'
        params = {'f': 'json', 'limit': 1000, 'bbox': ','.join(map(str, BBOX))}
        for _ in range(20):
            data = await get(client, url, **params)
            for f in data['features']:
                p = f['properties']
                if p.get('parameter_code') in ['00060', '00065'] and recent(p.get('time'), 6):
                    add(p.get('time_series_id', f.get('id')), f"Water gauge {p.get('monitoring_location_id')}",
                        f"{p.get('value')} {p.get('unit_of_measure')} ({'streamflow' if p['parameter_code'] == '00060' else 'gauge height'})",
                        f.get('geometry'), kind='observation', event_category='river', observed_at=p.get('time'),
                        updated_at=p.get('last_modified'), source_url=url, attributes=p)
            next_url = next((link['href'] for link in data.get('links', []) if link.get('rel') == 'next'), None)
            if not next_url:
                break
            if not next_url.startswith('https://api.waterdata.usgs.gov/'):
                raise ValueError('Unexpected pagination host')
            url, params = next_url, {}
        else:
            raise ValueError('USGS pagination limit exceeded')
    elif source == 'dallas_police':
        url = 'https://www.dallasopendata.com/resource/9fxf-t2tr.json'
        seen = set()
        budget = [GEOCODE_MAX_NEW]
        for offset in range(0, 10000, 1000):
            rows = await get(client, url, **{'$limit': 1000, '$offset': offset, '$order': 'incident_number'})
            for p in rows:
                identifier = p.get('incident_number')
                if identifier in seen:
                    continue
                seen.add(identifier)
                geometry, located = None, None
                if p.get('longitude') and p.get('latitude'):
                    geometry = point(p['longitude'], p['latitude'])
                else:
                    address = police_address(p)
                    hit = await geocode(client, address, budget) if address else None
                    if hit and hit['lon'] is not None:
                        geometry, located = point(hit['lon'], hit['lat']), hit
                observed = None
                try:
                    observed = datetime.fromisoformat(p['date'][:10] + 'T' + p['time']).replace(tzinfo=ZoneInfo('America/Chicago')).astimezone(timezone.utc).isoformat()
                except (KeyError, ValueError):
                    pass
                description = f"{p.get('status', 'Status unknown')} — {p.get('block', '')} {p.get('location', '')}".strip()
                attributes = {k: p.get(k) for k in ['priority', 'division', 'status', 'block', 'location']}
                if located:
                    level = 'intersection' if located['accuracy'] == 'geocoded_intersection' else 'block'
                    description += f". Approximate {level}-level location from the street name ({located['match']})."
                    if any(word in str(p.get('location', '')).upper() for word in [' FWY', ' EXPY', ' HWY', ' TOLLWAY', ' PKWY']):
                        description += ' Freeway side or direction may differ.'
                    attributes.update(geocode_match=located['match'], geocode_score=located['score'])
                args = (identifier, p.get('nature_of_call', 'Police call'), description)
                kwargs = dict(kind='incident', event_category='police', observed_at=observed, source_url=url, attributes=attributes)
                item = record(source, *args, geometry, **kwargs)
                if item is None and geometry:
                    # A match outside the configured region stays listed as unlocated rather than vanishing.
                    item, located = record(source, *args, None, **kwargs), None
                if item:
                    if located:
                        item['location_accuracy'] = located['accuracy']
                    items.append(item)
            if len(rows) < 1000:
                break
        else:
            raise ValueError('Police pagination limit exceeded')
    elif source == 'iem':
        url = 'https://mesonet.agron.iastate.edu/geojson/lsr.php'
        data = await get(client, url, sts=(now()-timedelta(hours=24)).strftime('%Y-%m-%dT%H:%MZ'),
                         ets=now().strftime('%Y-%m-%dT%H:%MZ'), wfos='FWD')
        for f in data['features']:
            p = f['properties']
            identifier = hashlib.sha256(json.dumps(f, sort_keys=True).encode()).hexdigest()[:20]
            add(identifier, p.get('typetext', 'Storm report'), p.get('remark'), f.get('geometry'),
                observed_at=p.get('valid'), source_url=url, attributes=p)
    elif source in ['nifc', 'fema_shelters']:
        url = ('https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query'
               if source == 'nifc' else 'https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query')
        for f in await arcgis(client, url):
            p = f['properties']
            if source == 'nifc':
                add(f.get('id', p.get('OBJECTID', hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:20])),
                    p.get('poly_IncidentName') or p.get('attr_IncidentName') or 'Fire perimeter',
                    'Published fire perimeter; perimeter age and current conditions must be verified.', f.get('geometry'),
                    event_category='wildfire', updated_at=p.get('poly_DateCurrent'), source_url=url,
                    attributes={k: p.get(k) for k in ['poly_GISAcres', 'attr_PercentContained', 'attr_IncidentTypeCategory']})
            else:
                add(p.get('shelter_id', f.get('id')), p.get('shelter_name') or 'Shelter',
                    f"{p.get('shelter_status', 'Unknown status')}; {p.get('address', '')}, {p.get('city', '')}. Call to verify availability.",
                    f.get('geometry'), kind='resource', event_category='shelter', source_url=url,
                    attributes={k: p.get(k) for k in ['shelter_status', 'evacuation_capacity', 'total_population', 'org_name', 'address']})
    elif source == 'earthquakes':
        url = 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson'
        data = await get(client, url)
        for f in data['features']:
            p = f['properties']
            coords = f['geometry']['coordinates']
            add(f['id'], p.get('title') or 'Earthquake', p.get('place'), point(*coords[:2]),
                event_category='earthquake', observed_at=p.get('time'), updated_at=p.get('updated'),
                source_url=p.get('url'), attributes={'magnitude': p.get('mag'), 'depth_km': coords[2], 'alert': p.get('alert'), 'mmi': p.get('mmi'),
                            'felt': p.get('felt'), 'tsunami': p.get('tsunami'), 'status': p.get('status')})
    elif source == 'dallas_gis':
        data = await get(client, 'https://gis.dallascityhall.com/arcgis/rest/services/Basemap/CityLimits/MapServer/0/query',
                         where='1=1', outFields='CITY', outSR=4326, geometryPrecision=5, f='geojson')
        boundaries = data['features']
    elif source == 'openfreemap':
        data = await get(client, STYLE)
        if 'sources' not in data:
            raise ValueError('Invalid map style')
    elif source == 'overpass':
        west, south, east, north = BBOX
        bbox = f'{south},{west},{north},{east}'
        query = f'[out:json][timeout:40];(nwr["amenity"~"^(fire_station|police|hospital|shelter|pharmacy)$"]({bbox});nwr["emergency"="ambulance_station"]({bbox}););out center tags;'
        response = await client.post('https://overpass-api.de/api/interpreter', data={'data': query}, timeout=60)
        response.raise_for_status()
        data = response.json()
        if data.get('remark'):
            raise ValueError(data['remark'])
        for p in data['elements']:
            tags = p.get('tags', {})
            if any(tags.get(k) not in [None, 'no'] for k in ['disused', 'abandoned', 'historic']):
                continue
            coordinates = p if 'lat' in p else p.get('center', {})
            if 'lat' not in coordinates:
                continue
            facility = tags.get('amenity') or tags.get('emergency', 'facility')
            add(f"{p['type']}/{p['id']}", tags.get('name') or facility.replace('_', ' ').title(),
                'Mapped facility. Operational status, staffing, dispatch availability and capacity are unverified.',
                point(coordinates['lon'], coordinates['lat']), kind='resource', event_category=facility,
                source_url=f"https://www.openstreetmap.org/{p['type']}/{p['id']}", attributes={'operational_status': 'unverified'})
    return {'items': [enrich_priority(enrich_water(item)) for item in items], 'boundaries': boundaries, 'fetched_at': now().isoformat(), 'bbox': list(BBOX)}


async def refresh(source, client):
    health[source]['last_attempt'] = now().isoformat()
    try:
        batch = await collect(source, client)
        snapshots[source] = batch
        health[source].update(status='ok', last_success=batch['fetched_at'], error=None)
        if source == 'dallas_police':
            save_geocodes()
        CACHE.mkdir(exist_ok=True)
        target = CACHE / f'{source}.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(batch), encoding='utf-8')
        temporary.replace(target)
    except Exception as exc:
        health[source].update(status='error', error=f'{type(exc).__name__}: {str(exc)[:250]}')
        logger.warning('%s failed: %s', source, health[source]['error'])


async def poll(source, client):
    snapshot = snapshots.get(source)
    if snapshot:
        elapsed = (now() - datetime.fromisoformat(snapshot['fetched_at'])).total_seconds()
        await asyncio.sleep(max(0, INTERVALS[source] - elapsed))
    while True:
        await refresh(source, client)
        await asyncio.sleep(INTERVALS[source])


@asynccontextmanager
async def lifespan(_app):
    for source in ENABLED:
        try:
            batch = json.loads((CACHE / f'{source}.json').read_text(encoding='utf-8'))
            if batch.get('bbox') == list(BBOX):
                batch['items'] = [enrich_priority(enrich_water(item)) for item in batch['items']]
                snapshots[source] = batch
                health[source].update(status='cached', last_success=batch['fetched_at'])
        except (OSError, ValueError, KeyError):
            pass
    try:
        geocodes.update(json.loads((CACHE / GEOCODE_FILE).read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    async with httpx.AsyncClient(timeout=45, limits=httpx.Limits(max_connections=8),
                                 headers={'User-Agent': os.getenv('UPSTREAM_USER_AGENT', 'TexasResponse-Hackathon/0.1'), 'Accept': 'application/json'}) as client:
        tasks = [asyncio.create_task(poll(source, client)) for source in ENABLED]
        tasks.append(asyncio.create_task(run_sync(snapshots, source_status, now, nemotron.prepare_for_sync)))
        tasks.append(asyncio.create_task(nemotron.run(snapshots, CACHE)))
        tasks.append(asyncio.create_task(resident_ai.run()))
        tasks.append(asyncio.create_task(issues.run(snapshots, source_status, CACHE)))
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title='Dallas Disaster Feed API', version='0.1.0', lifespan=lifespan,
              description='Independent cached public feeds. Empty results do not imply safety; consult /sources for coverage and freshness.')
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','), allow_methods=['GET'], allow_headers=['*'])


def source_status():
    result = {}
    for source, state in health.items():
        age = (now()-datetime.fromisoformat(state['last_success'])).total_seconds() if state['last_success'] else None
        result[source] = {**state, 'interval_seconds': INTERVALS[source], 'age_seconds': round(age, 1) if age is not None else None,
                          'stale': age is None or age > INTERVALS[source] * 2 or state['status'] == 'error',
                          'record_count': len(snapshots.get(source, {}).get('items', []))}
    return result


@app.get('/health')
def health_endpoint():
    states = source_status()
    return {'status': 'ok' if all(s['status'] == 'ok' and not s['stale'] for s in states.values()) else 'degraded',
            'service': 'running', 'ready_sources': sum(s['last_success'] is not None for s in states.values()), 'total_sources': len(states),
            'spacetime_sync': sync_state, 'nemotron': nemotron.state, 'resident_ai': resident_ai.state, 'issue_analysis': issues.state}


@app.get('/issues')
def issues_endpoint(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    current = [card for card in issues.cards if datetime.fromisoformat(card['expires_at']) > now()]
    current.sort(key=lambda card: (-issues.LEVELS.index(card['level']), card['id']))
    return {'issues': current[offset:offset+limit], 'total': len(current), 'offset': offset, 'limit': limit, 'analysis': issues.state}


@app.get('/sources')
def sources_endpoint():
    return {'sources': source_status()}


@app.get('/pins')
def pins_endpoint(source: str | None = None, category: str | None = None, kind: str | None = None,
                  include_stale: bool = True, limit: int = Query(1000, ge=1, le=10000), offset: int = Query(0, ge=0)):
    states = source_status()
    pins, unlocated = [], []
    for key, batch in sorted(snapshots.items()):
        if source and source != key:
            continue
        for original in batch['items']:
            item = nemotron.attach(enrich_priority(enrich_water({**original, 'fetched_at': batch['fetched_at'], 'stale': states[key]['stale']})))
            if item['expires_at'] and datetime.fromisoformat(item['expires_at']) <= now():
                continue
            if item['source'] in ['nwps', 'usgs_water'] and not recent(item['observed_at'], 6):
                continue
            if item['source'] in ['iem', 'earthquakes'] and not recent(item['observed_at'], 24):
                continue
            if (category and category != item['category']) or (kind and kind != item['kind']) or (not include_stale and item['stale']):
                continue
            (pins if item['latitude'] is not None else unlocated).append(item)
    return {'generated_at': now().isoformat(), 'bbox': BBOX, 'total': len(pins), 'offset': offset, 'limit': limit,
            'pins': pins[offset:offset+limit], 'unlocated_total': len(unlocated), 'unlocated': unlocated[offset:offset+limit],
            'sources': states}


@app.get('/geojson')
def geojson_endpoint(source: str | None = None):
    data = pins_endpoint(source=source, limit=10000, offset=0)
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'id': p['id'], 'geometry': p['geometry'],
         'properties': {k: v for k, v in p.items() if k != 'geometry'}} for p in data['pins']],
        'total': data['total'], 'truncated': data['total'] > 10000, 'sources': data['sources']}


@app.get('/boundaries')
def boundaries_endpoint():
    return {'type': 'FeatureCollection', 'features': snapshots.get('dallas_gis', {}).get('boundaries', []),
            'source_status': source_status().get('dallas_gis')}


@app.get('/map-config')
def map_config_endpoint():
    return {'style_url': STYLE, 'center': [-96.7970, 32.7767], 'bbox': BBOX,
            'coordinate_order': 'GeoJSON uses [longitude, latitude]', 'boundaries_url': '/boundaries',
            'features_url': '/geojson', 'attribution': '© OpenStreetMap contributors; OpenFreeMap; individual data providers'}
