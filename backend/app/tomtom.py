"""Regional traffic incidents; never expose credential-bearing request URLs."""
import math
import os
from datetime import timedelta
import httpx
from .extra_feeds import parse_time

URL = 'https://api.tomtom.com/traffic/services/5/incidentDetails'
FIELDS = '{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code},startTime,endTime,from,to,length,delay,roadNumbers,timeValidity,probabilityOfOccurrence,lastReportTime}}}'
CATEGORIES = {0: 'Traffic incident', 1: 'Reported crash', 2: 'Road fog', 3: 'Dangerous road conditions',
              4: 'Road rain conditions', 5: 'Road ice', 6: 'Traffic congestion', 7: 'Lane closure',
              8: 'Road closure', 9: 'Roadworks', 10: 'Road wind conditions', 11: 'Road flooding', 14: 'Broken-down vehicle'}


def boxes(bbox):
    west, south, east, north = bbox
    area = (east-west)*111.32*math.cos(math.radians((south+north)/2))*(north-south)*111.32
    count = max(1, math.ceil(area/9000))  # TomTom permits at most 10,000 square km per query.
    if count > 16:
        raise ValueError('Traffic region too large; refusing excessive API requests')
    width = (east-west)/count
    return [(west+i*width, south, west+(i+1)*width, north) for i in range(count)]


async def collect_tomtom(client, bbox, record, at):
    key = os.getenv('TOMTOM_API_KEY', '').strip()
    if not key:
        raise ValueError('TOMTOM_API_KEY is missing; configure backend/.env and restart')
    incidents = []
    for bounds in boxes(bbox):
        try:
            response = await client.get(URL, params={'key': key, 'bbox': ','.join(map(str, bounds)),
                'fields': FIELDS, 'language': 'en-US', 'timeValidityFilter': 'present'})
            if response.status_code != 200:
                raise ValueError(f'TomTom HTTP {response.status_code}; check account access or quota')
            data = response.json()
        except httpx.HTTPError as exc:
            raise ValueError(f'TomTom network failure ({type(exc).__name__})') from None
        except ValueError as exc:
            if str(exc).startswith('TomTom HTTP'):
                raise
            raise ValueError('TomTom returned invalid JSON') from None
        if not isinstance(data, dict) or not isinstance(data.get('incidents'), list):
            raise ValueError('TomTom returned an unexpected response')
        if len(data['incidents']) >= 10000:
            raise ValueError('TomTom response too large; snapshot not replaced')
        incidents.extend(data['incidents'])
    items, seen = [], set()
    for feature in incidents:
        p = feature['properties']
        identifier = p.get('id')
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        start, end = parse_time(p.get('startTime')), parse_time(p.get('endTime'))
        if start and start > at or end and end <= at or p.get('timeValidity') == 'future':
            continue
        category = CATEGORIES.get(p.get('iconCategory'), 'Traffic incident')
        events = [e['description'] for e in p.get('events', []) if isinstance(e.get('description'), str)]
        road = ' to '.join(str(p[k]) for k in ['from', 'to'] if p.get(k))
        description = '. '.join([*events, road, 'Traffic-provider report; current impact is not independently verified. © TomTom.'])
        expiry = min(end, at+timedelta(hours=1)) if end else at+timedelta(hours=1)
        item = record('tomtom', str(identifier), category, description, feature.get('geometry'), kind='incident',
            event_category='traffic_hazard', observed_at=start.isoformat() if start else None,
            updated_at=p.get('lastReportTime'), expires_at=expiry.isoformat(), source_url='https://www.tomtom.com/traffic-index/',
            attributes={'icon_category': p.get('iconCategory'), 'magnitude_of_delay': p.get('magnitudeOfDelay'),
                        'delay_seconds': p.get('delay'), 'length_meters': p.get('length'), 'road_numbers': p.get('roadNumbers', []),
                        'events': p.get('events', []), 'from': p.get('from'), 'to': p.get('to'),
                        'probability': p.get('probabilityOfOccurrence'), 'verification': 'traffic_provider_report',
                        'attribution': '© TomTom'})
        if item:
            items.append(item)
    return items
