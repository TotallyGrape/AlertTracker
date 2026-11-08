import asyncio
from datetime import datetime, timezone, timedelta
import httpx
import pytest
from app import main as m
from app.tomtom import boxes, collect_tomtom

AT = datetime.now(timezone.utc)


def feature(identifier='test', **properties):
    return {'geometry': {'type': 'LineString', 'coordinates': [[-96.8,32.8],[-96.7,32.81]]},
            'properties': {'id': identifier, 'iconCategory': 1, 'startTime': (AT-timedelta(hours=1)).isoformat(),
                           'endTime': (AT+timedelta(days=1)).isoformat(), 'events': [{'description': 'Accident reported'}], **properties}}


def run(handler, monkeypatch):
    monkeypatch.setenv('TOMTOM_API_KEY', 'test-secret-not-for-logs')
    async def collect():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await collect_tomtom(client, m.BBOX, m.record, AT)
    return asyncio.run(collect())


def test_split_deduplication_line_geometry_and_expiry(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'incidents': [feature()]})
    items = run(handler, monkeypatch)
    assert len(calls) == len(boxes(m.BBOX)) == 2
    assert len(items) == 1 and items[0]['geometry']['type'] == 'LineString'
    assert items[0]['expires_at'] == (AT+timedelta(hours=1)).isoformat()
    assert items[0]['name'] == 'Reported crash' and items[0]['attributes']['attribution'] == '© TomTom'
    assert all(r.url.params['timeValidityFilter'] == 'present' for r in calls)


def test_future_expired_and_outside_incidents_are_not_returned(monkeypatch):
    outside = feature('outside'); outside['geometry']['coordinates'] = [[0,0],[1,1]]
    items = run(lambda _: httpx.Response(200, json={'incidents': [feature('future', startTime=(AT+timedelta(days=1)).isoformat()),
                   feature('expired', endTime=(AT-timedelta(seconds=1)).isoformat()), outside]}), monkeypatch)
    assert items == []


@pytest.mark.parametrize('status', [401,403,429,500])
def test_errors_do_not_leak_key(monkeypatch, status):
    with pytest.raises(ValueError) as caught:
        run(lambda _: httpx.Response(status), monkeypatch)
    assert f'HTTP {status}' in str(caught.value)
    assert 'test-secret-not-for-logs' not in str(caught.value)


def test_timeout_does_not_leak_request_url(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout(str(request.url), request=request)
    with pytest.raises(ValueError) as caught:
        run(handler, monkeypatch)
    assert 'test-secret-not-for-logs' not in str(caught.value)
