import asyncio
from datetime import timedelta

import httpx
from fastapi.testclient import TestClient
from shapely.geometry import shape

from app import main as m


def test_geometry_filter_and_representative_point():
    assert m.record('test', 'outside', 'Outside', '', m.point(0, 0)) is None
    polygon = {'type': 'Polygon', 'coordinates': [[[-97, 32.7], [-96.8, 32.7], [-96.8, 32.9], [-97, 32.9], [-97, 32.7]]]}
    pin = m.record('test', 'inside', 'Flood', 'Description', polygon)
    assert pin['geometry']['type'] == 'Polygon'
    assert shape(polygon).contains(shape(m.point(pin['longitude'], pin['latitude'])))


def test_police_dedup_and_no_invented_coordinates():
    async def run():
        def handler(request):
            return httpx.Response(200, json=[{'incident_number': '123', 'nature_of_call': 'ASSIST', 'location': 'MAIN ST'},
                                             {'incident_number': '123', 'nature_of_call': 'ASSIST'}])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            batch = await m.collect('dallas_police', client)
        assert len(batch['items']) == 1
        assert batch['items'][0]['latitude'] is None
    asyncio.run(run())


def police_client(rows, candidates_for, calls):
    """Mock Socrata + Dallas locator. candidates_for(address) returns the locator's candidate list."""
    def handler(request):
        if 'GeocodeServer' in str(request.url):
            address = request.url.params['Single Line Input']
            calls.append(address)
            return httpx.Response(200, json={'candidates': candidates_for(address)})
        return httpx.Response(200, json=rows)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def candidate(address, kind, score=100, x=-96.75, y=32.78):
    return [{'address': address, 'score': score, 'location': {'x': x, 'y': y}, 'attributes': {'Addr_type': kind}}]


def test_police_calls_geocoded_to_block_and_intersection(monkeypatch):
    monkeypatch.setattr(m, 'geocodes', {})
    rows = [{'incident_number': '1', 'nature_of_call': 'Major Accident', 'block': '1400', 'location': 'PEABODY AVE'},
            {'incident_number': '2', 'nature_of_call': 'Major Accident', 'location': 'Scyene Rd / Urban Ave'},
            {'incident_number': '3', 'nature_of_call': 'Freeway', 'block': '6400', 'location': 'E R L Thornton Fwy Wb'}]
    def candidates_for(address):
        return candidate(address.upper(), 'StreetInt' if '&' in address else 'StreetAddress')
    calls = []
    async def run():
        async with police_client(rows, candidates_for, calls) as client:
            return await m.collect('dallas_police', client)
    items = {i['id']: i for i in asyncio.run(run())['items']}
    assert calls == ['1400 PEABODY AVE', 'Scyene Rd & Urban Ave', '6400 E R L Thornton Fwy Wb']
    assert items['dallas_police:1']['location_accuracy'] == 'geocoded_block'
    assert (items['dallas_police:1']['longitude'], items['dallas_police:1']['latitude']) == (-96.75, 32.78)
    assert items['dallas_police:2']['location_accuracy'] == 'geocoded_intersection'
    assert 'Freeway side or direction may differ' in items['dallas_police:3']['description']
    assert items['dallas_police:1']['attributes']['geocode_score'] == 100


def test_police_geocode_rejects_weak_matches_and_uses_cache(monkeypatch):
    monkeypatch.setattr(m, 'geocodes', {})
    rows = [{'incident_number': '1', 'block': '100', 'location': 'NOWHERE RD'},
            {'incident_number': '2', 'block': '200', 'location': 'MAIN ST'},
            {'incident_number': '3', 'block': '300', 'location': 'ELM ST'},
            {'incident_number': '4', 'location': 'COMMERCE ST'}]  # street name only: never looked up
    def candidates_for(address):
        if 'NOWHERE' in address:
            return candidate(address, 'StreetAddress', score=72)
        if 'MAIN' in address:
            return candidate(address, 'StreetName')  # whole-street match is too vague
        return candidate(address, 'StreetAddress', x=-50, y=10)  # outside the region
    calls = []
    async def run():
        async with police_client(rows, candidates_for, calls) as client:
            first = await m.collect('dallas_police', client)
            second = await m.collect('dallas_police', client)
        return first, second
    first, second = asyncio.run(run())
    assert len(first['items']) == 4 and all(i['latitude'] is None for i in first['items'])
    assert len(calls) == 3  # second poll reused the cached results
    assert len(second['items']) == 4 and all(i['latitude'] is None for i in second['items'])


def test_police_geocoder_outage_does_not_fail_refresh(monkeypatch):
    monkeypatch.setattr(m, 'geocodes', {})
    def handler(request):
        if 'GeocodeServer' in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200, json=[{'incident_number': '1', 'block': '1400', 'location': 'PEABODY AVE'}])
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await m.collect('dallas_police', client)
    items = asyncio.run(run())['items']
    assert len(items) == 1 and items[0]['latitude'] is None
    assert m.geocodes == {}  # transient failure is not cached as a miss


def test_failure_retains_snapshot_and_marks_stale(monkeypatch):
    async def fail(*args):
        raise RuntimeError('upstream unavailable')
    monkeypatch.setattr(m, 'collect', fail)
    saved = {'items': [], 'fetched_at': m.now().isoformat(), 'bbox': list(m.BBOX)}
    monkeypatch.setattr(m, 'snapshots', {'nws_alerts': saved})
    monkeypatch.setattr(m, 'health', {'nws_alerts': {'status': 'ok', 'last_success': saved['fetched_at'], 'last_attempt': None, 'error': None}})
    asyncio.run(m.refresh('nws_alerts', None))
    assert m.snapshots['nws_alerts'] is saved
    assert m.source_status()['nws_alerts']['stale']


def test_endpoints_expiry_and_geojson(monkeypatch):
    valid = m.record('nws_alerts', 'a', 'Flood', 'Test', m.point(-96.8, 32.8), kind='warning')
    expired = {**valid, 'id': 'expired', 'expires_at': (m.now()-timedelta(seconds=1)).isoformat()}
    missing = m.record('nws_alerts', 'b', 'Unknown location', '')
    fetched = m.now().isoformat()
    monkeypatch.setattr(m, 'snapshots', {'nws_alerts': {'items': [valid, expired, missing], 'fetched_at': fetched}})
    monkeypatch.setattr(m, 'health', {'nws_alerts': {'status': 'ok', 'last_success': fetched, 'last_attempt': fetched, 'error': None}})
    client = TestClient(m.app)  # No lifespan: no network access in tests.
    data = client.get('/pins').json()
    assert data['total'] == 1 and data['unlocated_total'] == 1
    assert client.get('/geojson').json()['features'][0]['geometry']['coordinates'] == [-96.8, 32.8]
    assert client.get('/pins?limit=0').status_code == 422
    assert client.get('/map-config').status_code == 200
    assert client.get('/openapi.json').status_code == 200


def test_old_water_observations_not_published():
    async def run():
        def handler(request):
            return httpx.Response(200, json={'features': [{'geometry': m.point(-96.8, 32.8), 'properties': {
                'parameter_code': '00065', 'time': '2015-01-01T00:00:00Z'}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await m.collect('usgs_water', client)
        assert result['items'] == []
    asyncio.run(run())
