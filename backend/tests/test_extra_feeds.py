import asyncio
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from app import main as m
from app import extra_feeds as e

AT = datetime(2026, 11, 8, 3, 0, tzinfo=timezone.utc)


def collect(source, payload, monkeypatch):
    monkeypatch.setattr(m, 'now', lambda: AT)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
            return await m.collect(source, client)
    return asyncio.run(run())['items']


def request(**overrides):
    return {'unique_key': 'stable-id', 'service_request_number': '26-123', 'service_request_type': 'Traffic Signal - Knockdown - TPW',
            'status': 'New', 'address': 'Dallas', 'created_date': '2026-11-07T03:00:00',
            'update_date': '2026-11-07T04:00:00', 'lat_location': '(32.8,-96.8)', **overrides}


def test_311_status_age_hazard_and_region_filters(monkeypatch):
    rows = [request(), request(), request(unique_key='closed', status='Closed'),
            request(unique_key='completed', closed_date='2026-11-07T05:00:00'),
            request(unique_key='old', created_date='2024-01-01T00:00:00'),
            request(unique_key='routine', service_request_type='Garbage pickup'),
            request(unique_key='utility-work', service_request_type='Water/Wastewater Line Locate - 311'),
            request(unique_key='planned-work', service_request_type='Traffic Signal - Modification - TPW'),
            request(unique_key='outside', lat_location='(30,-100)')]
    items = collect('dallas_311', rows, monkeypatch)
    assert len(items) == 1 and items[0]['id'] == 'dallas_311:stable-id'
    assert items[0]['observed_at'] == '2026-11-07T09:00:00+00:00'
    assert items[0]['category'] == 'traffic_hazard'
    assert items[0]['attributes']['verification'] == 'unverified_report'


def test_311_missing_location_remains_unlocated_and_pagination_is_bounded(monkeypatch):
    assert collect('dallas_311', [request(lat_location='')], monkeypatch)[0]['latitude'] is None
    monkeypatch.setattr(e, 'PAGE_SIZE', 1)
    monkeypatch.setattr(e, 'MAX_PAGES', 1)
    with pytest.raises(ValueError, match='pagination limit'):
        collect('dallas_311', [request()], monkeypatch)


def event(**overrides):
    return {'id': 'EONET_TEST', 'title': 'Test wildfire', 'closed': None, 'categories': [{'id': 'wildfires'}],
            'geometry': [{'type': 'Point', 'coordinates': [-96.8, 32.8], 'date': AT.isoformat()}], **overrides}


def test_eonet_uses_latest_geometry_not_historical_local_point(monkeypatch):
    moving = event(id='moving', geometry=[{'type': 'Point', 'coordinates': [-96.8, 32.8], 'date': (AT-timedelta(days=1)).isoformat()},
                                         {'type': 'Point', 'coordinates': [-100, 30], 'date': AT.isoformat()}])
    items = collect('eonet', {'events': [event(), event(), moving, event(id='closed', closed=AT.isoformat())]}, monkeypatch)
    assert len(items) == 1 and items[0]['category'] == 'wildfire'


def test_eonet_preserves_area_geometry_and_rejects_old_points(monkeypatch):
    polygon = {'type': 'Polygon', 'coordinates': [[[-97,32.7],[-96.8,32.7],[-96.8,32.9],[-97,32.9],[-97,32.7]]], 'date': AT.isoformat()}
    old = event(id='old', geometry=[{'type': 'Point', 'coordinates': [-96.8,32.8], 'date': (AT-timedelta(days=15)).isoformat()}])
    items = collect('eonet', {'events': [event(geometry=[polygon]), old]}, monkeypatch)
    assert len(items) == 1 and items[0]['geometry']['type'] == 'Polygon'


def test_empty_feed_is_success_but_provider_error_is_not(monkeypatch):
    assert collect('eonet', {'events': []}, monkeypatch) == []
    assert collect('dallas_311', [], monkeypatch) == []
    with pytest.raises(ValueError, match='error payload'):
        collect('dallas_311', {'error': True}, monkeypatch)
