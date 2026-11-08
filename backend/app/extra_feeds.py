"""Anonymous supplemental feeds. These describe reports/events, not verified dispatch needs."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DALLAS_311_URL = 'https://www.dallasopendata.com/resource/d7e7-envw.json'
EONET_URL = 'https://eonet.gsfc.nasa.gov/api/v3/events'
PAGE_SIZE = 1000
MAX_PAGES = 10
HAZARD_TERMS = ('FLOOD', 'DRAINAGE', 'TRAFFIC SIGNAL', 'WATER MAIN', 'WATER LEAK', 'SEWER', 'WASTEWATER', 'TREE DOWN', 'FALLEN TREE')
ROUTINE_TERMS = ('LINE LOCATE', 'MODIFICATION', 'PROJECT', 'INQUIRY', 'TRAFFIC SIGNAL - NEW', 'CLEANING/REPAIRS')


def parse_time(value, local=False):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo('America/Chicago') if local else timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


async def fetch_json(client, url, params):
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and (data.get('error') or data.get('errorCode')):
        raise ValueError('Provider returned an error payload')
    return data


async def collect_311(client, bbox, record, at):
    cutoff = at - timedelta(days=7)
    local_cutoff = cutoff.astimezone(ZoneInfo('America/Chicago')).strftime('%Y-%m-%dT%H:%M:%S')
    where = "created_date >= '" + local_cutoff + "' AND closed_date IS NULL AND (" + ' OR '.join(
        f"upper(service_request_type) like '%{term}%'" for term in HAZARD_TERMS) + ') AND ' + ' AND '.join(
        f"upper(service_request_type) not like '%{term}%'" for term in ROUTINE_TERMS)
    items, seen = [], set()
    for page in range(MAX_PAGES):
        rows = await fetch_json(client, DALLAS_311_URL, {
            '$where': where, '$order': 'created_date DESC, unique_key ASC', '$limit': PAGE_SIZE, '$offset': page * PAGE_SIZE,
            '$select': 'unique_key,service_request_number,service_request_type,address,status,created_date,update_date,closed_date,lat_location,department'})
        if not isinstance(rows, list):
            raise ValueError('Unexpected Dallas 311 response')
        for row in rows:
            created = parse_time(row.get('created_date'), local=True)
            title = str(row.get('service_request_type', ''))
            identifier = row.get('unique_key') or row.get('service_request_number')
            status = str(row.get('status', 'unknown'))
            if (not identifier or identifier in seen or not created or not cutoff <= created <= at + timedelta(minutes=10)
                    or row.get('closed_date') or status.lower() in ['closed', 'cancelled', 'canceled', 'resolved']
                    or not any(term in title.upper() for term in HAZARD_TERMS)
                    or any(term in title.upper() for term in ROUTINE_TERMS)):
                continue
            seen.add(identifier)
            geometry = None
            coords = re.fullmatch(r'\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)\s*', str(row.get('lat_location', '')))
            if coords:
                lat, lon = map(float, coords.groups())
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                geometry = {'type': 'Point', 'coordinates': [lon, lat]}
            lower = title.lower()
            category = 'flood' if 'flood' in lower or 'drainage' in lower else 'traffic_hazard' if 'traffic signal' in lower else 'infrastructure'
            updated = parse_time(row.get('update_date'), local=True)
            item = record('dallas_311', str(identifier), title,
                          f"Community service request: {status}. {row.get('address', '')}. Delayed public report; current hazard is unverified.",
                          geometry, kind='incident', event_category=category, observed_at=created.isoformat(),
                          updated_at=updated.isoformat() if updated else None, expires_at=(created+timedelta(days=7)).isoformat(),
                          source_url='https://www.dallasopendata.com/d/d7e7-envw',
                          attributes={'request_number': row.get('service_request_number'), 'status': status,
                                      'address': row.get('address'), 'department': row.get('department'),
                                      'verification': 'unverified_report', 'publication_delay': 'not_live_dispatch'})
            if item:
                # Normalizer performs the final bbox intersection, including coordinate-less records.
                items.append(item)
        if len(rows) < PAGE_SIZE:
            return items
    raise ValueError('Dallas 311 pagination limit reached; previous snapshot retained')


async def collect_eonet(client, bbox, record, at):
    west, south, east, north = bbox
    data = await fetch_json(client, EONET_URL, {'status': 'open', 'days': 14, 'limit': 1000,
                                              'bbox': f'{west},{north},{east},{south}'})
    events = data['events']
    if not isinstance(events, list) or len(events) >= 1000:
        raise ValueError('EONET result limit reached or invalid response; snapshot not replaced')
    items, seen = [], set()
    for event in events:
        if event.get('closed') or not event.get('id') or event['id'] in seen:
            continue
        seen.add(event['id'])
        geometries = [(parse_time(g.get('date')), g) for g in event.get('geometry', [])]
        geometries = [(date, geometry) for date, geometry in geometries if date and date <= at + timedelta(minutes=10)]
        if not geometries:
            continue
        # A moving event's OLD point in Dallas is not evidence it is still in Dallas.
        observed, geometry = max(geometries, key=lambda pair: pair[0])
        if observed < at-timedelta(days=14) or geometry.get('type') not in ['Point', 'Polygon', 'MultiPolygon']:
            continue
        category_ids = [category.get('id') for category in event.get('categories', [])]
        category_map = {'wildfires': 'wildfire', 'severeStorms': 'severe_weather', 'floods': 'flood', 'landslides': 'landslide',
                        'volcanoes': 'volcano', 'earthquakes': 'earthquake', 'dustHaze': 'air_quality', 'drought': 'drought'}
        category = next((category_map[c] for c in category_ids if c in category_map), 'natural_event')
        item = record('eonet', event['id'], event.get('title') or 'Natural event',
                      (event.get('description') or 'NASA-curated natural event.') + ' Latest published event location; not a local dispatch alert.',
                      {'type': geometry['type'], 'coordinates': geometry['coordinates']}, kind='incident', event_category=category,
                      observed_at=observed.isoformat(), updated_at=observed.isoformat(),
                      expires_at=(observed+timedelta(days=14)).isoformat(), source_url=f"{EONET_URL}/{event['id']}",
                      attributes={'categories': event.get('categories', []), 'references': event.get('sources', []),
                                  'magnitude_value': geometry.get('magnitudeValue'), 'magnitude_unit': geometry.get('magnitudeUnit'),
                                  'verification': 'curated_event', 'location_scope': 'latest_published_geometry'})
        if item:
            items.append(item)
    return items
