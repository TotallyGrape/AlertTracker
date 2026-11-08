from datetime import datetime, timedelta, timezone

from app.priority import assess, enrich_priority

AT = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)


def nws(event, severity='Severe', urgency='Immediate', certainty='Observed', description='', area='Dallas, TX'):
    return {'source': 'nws_alerts', 'kind': 'warning', 'name': event, 'description': description, 'latitude': 32.8,
            'attributes': {'severity': severity, 'urgency': urgency, 'certainty': certainty, 'areaDesc': area}}


def police(call, priority, minutes_ago=10, location='MAIN ST', status='At Scene'):
    return {'source': 'dallas_police', 'kind': 'incident', 'name': call, 'latitude': 32.8,
            'observed_at': (AT - timedelta(minutes=minutes_ago)).isoformat(),
            'attributes': {'priority': priority, 'location': location, 'status': status}}


def storm(kind, magf=None, unit=None, remark='', hours_ago=1):
    return {'source': 'iem', 'kind': 'incident', 'name': kind, 'latitude': 32.8,
            'observed_at': (AT - timedelta(hours=hours_ago)).isoformat(),
            'attributes': {'magf': magf, 'unit': unit, 'remark': remark}}


def score(item):
    return assess(item, AT)['score']


def test_scores_stay_in_range_and_explain_themselves():
    for item in [nws('Tornado Emergency', 'Extreme'), nws('Special Weather Statement', 'Minor', 'Past', 'Unlikely', area='Collin'),
                 police('41/40 - Other', '4', minutes_ago=600), storm('TORNADO', remark='fatalities, people trapped, homes destroyed')]:
        result = assess(item, AT)
        assert 1 <= result['score'] <= 10 and result['reasons'] and result['basis'] == 'rules-v1'
        assert result['label'] in {'Critical', 'High', 'Elevated', 'Moderate', 'Low'}


def test_nws_ordering_uses_event_and_severity_fields():
    assert score(nws('Tornado Emergency', 'Extreme')) == 10
    assert score(nws('Tornado Warning')) >= 9
    assert score(nws('Flash Flood Warning', description='This is a LIFE THREATENING situation')) > score(nws('Flood Advisory', 'Minor', 'Expected', 'Likely'))
    assert score(nws('Severe Thunderstorm Watch', 'Severe', 'Future', 'Possible')) < score(nws('Severe Thunderstorm Warning'))
    assert score(nws('Flood Advisory', 'Minor', 'Expected', 'Likely', area='Denton')) <= 4


def test_police_priority_call_type_and_age():
    shooting = police('DASF-Dist Active Shooter Foot', '1')
    assert score(shooting) == 9  # single police call is capped below regional emergencies
    assert score(police('7XF - Major Accident Freeway', '2', location='N STEMMONS FWY NB')) == 6
    assert score(police('38 - Meet Complainant', '3')) == 3
    assert score(police('38 - Meet Complainant', '3', minutes_ago=300)) == 2
    assert score(police('41/40 - Other - In Progress', '2')) > score(police('41/40 - Other', '2'))


def test_storm_reports_use_size_remarks_and_age():
    assert score(storm('HAIL', 2.5, 'INCH')) > score(storm('HAIL', 0.75, 'INCH'))
    assert score(storm('TSTM WND GST', 80, 'MPH')) > score(storm('NON-TSTM WND GST', 45, 'MPH'))
    assert score(storm('FLASH FLOOD', remark='Water rescue in progress, cars stalled')) == 10
    assert score(storm('FLASH FLOOD', hours_ago=18)) < score(storm('FLASH FLOOD'))


def test_wildfire_and_earthquake_fields():
    fire = {'source': 'nifc', 'kind': 'incident', 'name': 'Creek Fire', 'latitude': 32.8,
            'attributes': {'poly_GISAcres': 12000, 'attr_PercentContained': 0}}
    burn = {**fire, 'attributes': {'poly_GISAcres': 40, 'attr_PercentContained': 95, 'attr_IncidentTypeCategory': 'RX'}}
    assert score(fire) >= 8 and score(burn) <= 2
    quake = {'source': 'earthquakes', 'kind': 'incident', 'name': 'M 1.1', 'latitude': 32.8, 'attributes': {'magnitude': 1.1, 'depth_km': 3}}
    strong = {**quake, 'attributes': {'magnitude': 5.4, 'depth_km': 4, 'alert': 'orange', 'mmi': 7.2, 'felt': 900}}
    assert score(quake) == 1 and score(strong) == 10


def test_facilities_shelters_and_readings_are_not_scored():
    for kind in ['resource', 'observation', 'forecast']:
        item = {'source': 'overpass', 'kind': kind, 'name': 'Walgreens'}
        assert assess(item, AT) is None and enrich_priority(item, AT) is item


def test_missing_fields_do_not_crash():
    for item in [{'source': 'iem', 'kind': 'incident', 'name': ''}, {'source': 'dallas_police', 'kind': 'incident'},
                 {'source': 'nws_alerts', 'kind': 'warning'}, {'source': 'earthquakes', 'kind': 'incident', 'attributes': {'magnitude': 'n/a'}},
                 {'source': 'new_feed', 'kind': 'warning', 'name': 'x'}]:
        assert 1 <= assess(item, AT)['score'] <= 10
