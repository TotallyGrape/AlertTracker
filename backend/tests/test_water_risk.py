from datetime import datetime, timezone, timedelta
import pytest
from app.water_risk import assess_water, enrich_water

NOW = datetime.now(timezone.utc)
THRESHOLDS = {'categories': {k: {'stage': v} for k, v in [('action', 29), ('minor', 30), ('moderate', 38), ('major', 40)]}}


@pytest.mark.parametrize('value,category,level', [(11, 'no_flooding', 'normal'), (29, 'no_flooding', 'caution'), (30, 'no_flooding', 'danger'), (38, 'moderate', 'danger'), (40, 'major', 'danger'), (-999, 'major', 'unknown')])
def test_local_thresholds_and_categories(value, category, level):
    assert assess_water('nwps', {'observed': {'primary': value, 'primaryUnit': 'ft', 'floodCategory': category}, 'flood_thresholds': THRESHOLDS}, NOW.isoformat(), NOW)['level'] == level


def test_different_units_unknown_thresholds_and_stale_data():
    attributes = {'observed': {'primary': 100, 'primaryUnit': 'kcfs'}, 'flood_thresholds': THRESHOLDS}
    assert assess_water('nwps', attributes, NOW.isoformat(), NOW)['level'] == 'unknown'
    assert assess_water('usgs_water', {}, NOW.isoformat(), NOW)['level'] == 'unknown'
    attributes['observed'].update(primaryUnit='ft', floodCategory='major')
    assert assess_water('nwps', attributes, (NOW-timedelta(hours=2)).isoformat(), NOW)['level'] == 'unknown'
    assert enrich_water({'source': 'nwps', 'attributes': attributes, 'observed_at': NOW.isoformat(), 'stale': True}, NOW)['risk']['level'] == 'unknown'
