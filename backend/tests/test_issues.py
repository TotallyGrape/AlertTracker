import json
from datetime import datetime, timedelta, timezone
import pytest
from app import issues as i

AT=datetime.now(timezone.utc)

def item(identifier='test:1', **extra):
    return {'id':identifier,'source':'tomtom','name':'Reported crash','description':'A crash has been reported on the road.',
        'kind':'incident','category':'traffic_hazard','latitude':32.8,'longitude':-96.8,
        'observed_at':AT.isoformat(),'updated_at':None,'expires_at':(AT+timedelta(hours=1)).isoformat(),
        'attributes':{'icon_category':1}, **extra}

def candidates(rows, stale=False):
    i.history.clear()
    return i.build_candidates({'tomtom':{'items':rows}}, {'tomtom':{'stale':stale}}, AT)

def reply(candidate, **extra):
    evidence=candidate['payload']['evidence'][0]
    return json.dumps({'title':'Reported traffic concern','summary':'A crash is reported in this area.', 'level':'active_threat',
        'evidence_ids':[evidence['id']], 'evidence_quotes':[{'id':evidence['id'],'quote':evidence['description']}],
        'uncertainty':'Current impact and independent confirmation are unavailable.', **extra})

def test_facilities_expired_and_stale_records_are_excluded():
    assert candidates([item(kind='resource')])==[]
    assert candidates([item(expires_at=(AT-timedelta(seconds=1)).isoformat())])==[]
    assert candidates([item()],stale=True)==[]

def test_grouping_deduplicates_ids_and_separates_location_and_hazard_family():
    groups=candidates([item(),item(),item('test:2',longitude=-97.3),item('test:3',category='river',source='usgs_water')])
    assert len(groups)==3
    assert sum(c['payload']['evidence_count'] for c in groups)==3

def test_unsupported_escalation_is_clamped_and_invented_evidence_rejected():
    candidate=candidates([item()])[0]
    result=i.validate(reply(candidate,level='critical'),candidate)
    assert result['level']=='active_threat' and result['guardrail_adjusted']
    assert i.validate(reply(candidate,uncertainty='Not independently verified; injuries are unknown.'),candidate)['level']=='active_threat'
    for extra in [{'evidence_ids':['made-up']},{'evidence_quotes':[{'id':'test:1','quote':'People are trapped'}]},
                  {'summary':'There are 999 casualties.'},{'summary':'This is a confirmed emergency.'}]:
        with pytest.raises(ValueError): i.validate(reply(candidate,**extra),candidate)

def test_gauges_alone_cannot_become_flood_danger_and_trends_need_history():
    i.history.clear()
    gauge=item('water:1',source='usgs_water',category='river',kind='observation',attributes={'parameter_code':'00065','value':'1','unit_of_measure':'ft'})
    assert i.track(gauge,AT) is None
    gauge['observed_at']=(AT+timedelta(minutes=10)).isoformat(); gauge['attributes']['value']='2'
    assert i.track(gauge,AT+timedelta(minutes=10)) is None
    gauge['observed_at']=(AT+timedelta(minutes=20)).isoformat(); gauge['attributes']['value']='3'
    trend=i.track(gauge,AT+timedelta(minutes=20))
    assert trend['direction']=='rising' and trend['samples']==3
    gauge['observed_at']=AT.isoformat()
    candidate=candidates([gauge])[0]
    assert candidate['payload']['rule_maximum']=='informational'

def test_official_warning_floor_and_area_context_are_preserved():
    warning=item('warning:1',source='nws_alerts',kind='warning',name='Tornado Warning',category='severe_weather',geometry=None)
    candidate=candidates([warning])[0]
    assert candidate['payload']['rule_minimum']=='critical'
    assert i.validate(reply(candidate,level='informational'),candidate)['level']=='critical'

def test_stable_risk_timestamps_do_not_trigger_repeated_inference():
    gauge=item('water:1',source='nwps',category='river',kind='observation',attributes={'observed':{'primary':10,'primaryUnit':'ft','floodCategory':'no_flooding'}})
    a=i.build_candidates({'tomtom':{'items':[gauge]}},{'tomtom':{'stale':False}},AT)[0]
    b=i.build_candidates({'tomtom':{'items':[gauge]}},{'tomtom':{'stale':False}},AT+timedelta(seconds=10))[0]
    assert a['fingerprint']==b['fingerprint']
