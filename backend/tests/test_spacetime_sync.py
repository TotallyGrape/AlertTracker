import asyncio
import httpx
import pytest
from app.spacetime_sync import sync_once

HEALTH = {'nws_alerts': {'status': 'ok', 'stale': False, 'last_success': '2026-11-07T20:00:00Z', 'interval_seconds': 60, 'error': None}}


def test_successful_empty_snapshot_is_sent_once_and_health_failure_does_not_clear_records():
    async def run():
        bodies = []
        def handler(request):
            import json
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={'accepted': True})
        sent = {}
        batches = {'nws_alerts': {'fetched_at': 'v1', 'items': []}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await sync_once(client, 'https://example.test/ingest', 'test', batches, HEALTH, sent)
            await sync_once(client, 'https://example.test/ingest', 'test', batches, HEALTH, sent)
            assert len(bodies) == 1 and bodies[0]['records'] == []
            failed = {'nws_alerts': {**HEALTH['nws_alerts'], 'status': 'error', 'stale': True}}
            await sync_once(client, 'https://example.test/ingest', 'test', batches, failed, sent)
            assert 'records' not in bodies[1]
    asyncio.run(run())


def test_failed_upload_is_not_acknowledged_and_can_retry():
    async def run():
        sent = {}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await sync_once(client, 'https://example.test/ingest', 'test', {}, HEALTH, sent)
        assert sent == {}
    asyncio.run(run())


def test_one_source_failure_does_not_prevent_other_sources_syncing():
    async def run():
        import json
        sent = {}
        sources = {**HEALTH, 'iem': HEALTH['nws_alerts']}
        def handler(request):
            source = json.loads(request.content)['source']
            return httpx.Response(503) if source == 'nws_alerts' else httpx.Response(200, json={'accepted': True})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await sync_once(client, 'https://example.test/ingest', 'test', {}, sources, sent)
        assert 'iem' in sent and 'nws_alerts' not in sent
    asyncio.run(run())
