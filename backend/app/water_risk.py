"""Explainable flood assessment using only the same gauge's official NOAA metadata."""
import math
from datetime import datetime, timezone, timedelta


def assess_water(source, attributes, observed_at, at=None):
    at = at or datetime.now(timezone.utc)
    def result(level, label, reason, **extra):
        return {'level': level, 'label': label, 'reason': reason, 'assessed_at': at.isoformat(),
                'basis': 'NOAA NWPS' if source == 'nwps' else 'USGS observation', **extra}
    try:
        measured = datetime.fromisoformat(str(observed_at).replace('Z', '+00:00'))
        if measured.tzinfo is None:
            raise ValueError('Timezone required')
        if not at - timedelta(hours=1) <= measured <= at + timedelta(minutes=10):
            return result('unknown', 'Unknown — outdated reading', 'A reading within the last hour is required for a current flood assessment.')
    except (ValueError, TypeError):
        return result('unknown', 'Unknown — observation time missing', 'Current conditions cannot be assessed without a valid timestamp.')
    if source != 'nwps':
        return result('unknown', 'Unknown — no verified flood thresholds', 'This USGS gauge has not been matched to official local flood thresholds. Its number alone cannot establish danger.')
    observed = attributes.get('observed', {})
    value = observed.get('primary')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= -900:
        return result('unknown', 'Unknown — reading unavailable', 'NOAA has not supplied a usable observation.')
    category = str(observed.get('floodCategory', '')).lower()
    if category in ['obs_not_current', 'out_of_service', 'not_defined', 'low_threshold']:
        return result('unknown', 'Unknown — flood status unavailable', f'NOAA reports {category.replace("_", " ")}; no current flood classification is assigned.')
    ranks = {'no_flooding': 0, 'action': 1, 'minor': 2, 'moderate': 3, 'major': 4}
    rank = ranks.get(category, -1)
    threshold_category = None
    # NWPS stage thresholds are in feet. Never compare streamflow or mismatched units to stage.
    thresholds = attributes.get('flood_thresholds', {}).get('categories', {})
    if observed.get('primaryUnit') == 'ft':
        for name in ['action', 'minor', 'moderate', 'major']:
            threshold = thresholds.get(name, {}).get('stage')
            if isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and math.isfinite(threshold) and threshold > -900 and value >= threshold:
                if ranks[name] > rank:
                    rank, threshold_category = ranks[name], name
    if rank < 0:
        return result('unknown', 'Unknown — no verified flood category', 'No usable official flood category or exceeded stage threshold is available.')
    effective = threshold_category or category
    extra = {'flood_category': effective, 'value': value, 'unit': observed.get('primaryUnit'),
             'threshold_stage_ft': thresholds.get(effective, {}).get('stage')}
    if rank >= 2:
        return result('danger', f'Danger — {effective} flooding',
                      f'NOAA reports {effective} flooding or the observation meets that gauge’s official {effective} flood stage.', **extra)
    if rank == 1:
        return result('caution', 'Caution — action stage', 'The gauge is at NOAA action stage: prepare for possible flooding. This is not a flood warning.', **extra)
    return result('normal', 'Below action stage / no flooding reported', 'NOAA reports no flooding at this gauge. This does not establish safety elsewhere.', **extra)


def enrich_water(item, at=None):
    if item.get('source') in ['nwps', 'usgs_water']:
        item = {**item, 'risk': assess_water(item['source'], item.get('attributes', {}), item.get('observed_at'), at)}
        if item.get('stale'):
            item['risk'] = {**item['risk'], 'level': 'unknown', 'label': 'Unknown — stale source', 'reason': 'The source is stale; verify the latest official conditions.'}
    return item
