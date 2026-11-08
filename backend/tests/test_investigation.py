import json
import asyncio
from datetime import timedelta
import pytest
from app.investigation import plan, query, investigate
from app import issues
from test_issues import item, candidates, AT, reply


def test_plan_limits_and_allowlist():
    assert plan('{"question":"Check nearby rivers?","tools":["river"]}')["tools"]==["river"]
    for tools in [["dispatch"],["weather","river","traffic"],["river","river"]]:
        with pytest.raises(ValueError): plan(json.dumps({"question":"Check?","tools":tools}))


def test_tool_rejects_stale_expired_and_distant_evidence():
    c=candidates([item()])[0]
    rows=[item('near'),item('far',longitude=-100),item('expired',expires_at=(AT-timedelta(seconds=1)).isoformat())]
    records,_=query('traffic',c,{'tomtom':{'items':rows}},{'tomtom':{'stale':False}},AT)
    assert [r['id'] for r in records]==['near']
    assert query('traffic',c,{'tomtom':{'items':rows}},{'tomtom':{'stale':True}},AT)[0]==[]


def test_workflow_adds_tool_evidence_for_validated_citations(monkeypatch):
    async def fake(*args,**kwargs): return '{"question":"Are nearby roads affected?","tools":["traffic"]}'
    monkeypatch.setattr('app.nemotron.call',fake)
    c=candidates([item('original')])[0]
    expanded=asyncio.run(investigate(None,'','','',c,{'tomtom':{'items':[item('tool:1')]}},{'tomtom':{'stale':False}},AT))
    assert c['payload']['evidence_count']==1
    assert expanded['payload']['investigation']['steps'][0]['evidence_ids']==['tool:1']
    assert len(expanded['payload']['evidence'])==2
    data=json.loads(reply(expanded)); data['evidence_ids']=['tool:1']; data['evidence_quotes']=[{'id':'tool:1','quote':'Reported crash'}]
    assert issues.validate(json.dumps(data),expanded)['level']=='active_threat'
