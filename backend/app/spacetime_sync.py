"""Private, retrying bridge. FastAPI remains independently usable when disabled."""
import asyncio
import hashlib
import json
import logging
import os
import time

import httpx

log = logging.getLogger('spacetime_sync')
state = {'enabled': False, 'status': 'disabled', 'last_success': None, 'error': None, 'source_errors': {}}


async def sync_once(client, url, secret, snapshots, sources, sent, prepare=None):
    """`prepare(source, items) -> (version_suffix, items)` lets enrichers (AI summaries) trigger a resend."""
    semaphore = asyncio.Semaphore(3)
    async def upload(source, health):
        # Age is recomputed every request; exclude it so it cannot cause constant uploads.
        health = {k: health[k] for k in ['status', 'stale', 'last_success', 'interval_seconds', 'error']}
        batch = snapshots.get(source)
        items, suffix = (batch or {}).get('items', []), ''
        if batch and prepare:
            suffix, items = prepare(source, items)
        version = f"{batch.get('fetched_at')}{'|' + suffix if suffix else ''}" if batch else None
        fingerprint = hashlib.sha256(json.dumps([version, health], sort_keys=True).encode()).hexdigest()
        if sent.get(source, {}).get('fingerprint') == fingerprint and time.monotonic() - sent[source].get('sent_at', 0) < 60:
            return
        body = {'source': source, 'health': health}
        if batch and sent.get(source, {}).get('version') != version:
            body['records'] = items
        async with semaphore:
            response = await client.post(url, headers={'x-ingest-secret': secret}, json=body)
        response.raise_for_status()
        if response.json().get('accepted') is not True:
            raise ValueError('Spacetime did not acknowledge snapshot')
        sent[source] = {'version': version, 'fingerprint': fingerprint, 'sent_at': time.monotonic()}
    results = await asyncio.gather(*(upload(source, health) for source, health in sources.items()), return_exceptions=True)
    state['source_errors'] = {source: type(result).__name__ for source, result in zip(sources, results) if isinstance(result, Exception)}
    failure = next((result for result in results if isinstance(result, Exception)), None)
    if failure:
        raise failure


async def run(snapshots, source_status, timestamp, prepare=None):
    url, secret = os.getenv('SPACETIME_INGEST_URL'), os.getenv('SPACETIME_INGEST_SECRET')
    if not url or not secret:
        return
    state.update(enabled=True, status='connecting')
    sent = {}
    async with httpx.AsyncClient(timeout=90, limits=httpx.Limits(max_connections=3, max_keepalive_connections=0)) as client:
        while True:
            try:
                await sync_once(client, url, secret, snapshots, source_status(), sent, prepare)
                state.update(status='ok', last_success=timestamp().isoformat(), error=None)
            except Exception as exc:
                # HTTPX exceptions can contain URLs, never log headers or request bodies.
                state.update(status='error', error=type(exc).__name__)
                log.warning('Spacetime synchronization failed (%s); retrying in 30 seconds', type(exc).__name__)
            await asyncio.sleep(30)
