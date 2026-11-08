import asyncio
from datetime import datetime,timezone
import httpx
from app.community import collect_community
from app import main as m,issues

def test_aggregate_only_feed_and_thresholds(monkeypatch):
    monkeypatch.setenv('SPACETIME_INGEST_URL','https://example.test/ingest')
    monkeypatch.setenv('SPACETIME_INGEST_SECRET','test')
    at=datetime.now(timezone.utc)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'clusters':[
            {'id':'cell','latitude':32.825,'longitude':-96.81,'report_count':3,'help_types':{'shelter':2,'evacuation':1}}]}))) as client:
            return await collect_community(client,m.record,at)
    items=asyncio.run(run())
    assert len(items)==1 and items[0]['location_accuracy']=='approximate_5km_area'
    assert items[0]['attributes']['demo_assumption'] is True
    candidates=issues.build_candidates({'community_reports':{'items':items}},{'community_reports':{'stale':False}},at)
    assert candidates[0]['payload']['rule_minimum']=='active_threat'
    assert candidates[0]['payload']['rule_maximum']=='active_threat'
    items[0]['attributes']['report_count']=2
    candidate=issues.build_candidates({'community_reports':{'items':items}},{'community_reports':{'stale':False}},at)[0]
    assert candidate['payload']['rule_minimum']=='caution'
