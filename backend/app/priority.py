"""Rule-based 1-10 danger priority for alert and incident pins (10 = most urgent danger).

Every rule reads only fields the provider supplied and records a short reason, so a coordinator can see why
a pin scored what it did. Facilities, shelters, readings and forecasts are not scored. This is a triage aid,
not an official severity: a low score never means a place is safe.
"""
import re
from datetime import datetime, timezone

VERSION = 'rules-v1'
SCORED_KINDS = {'warning', 'incident'}


def _num(value):
    try:
        number = float(value)
        return number if number == number else None  # drop NaN
    except (TypeError, ValueError):
        return None


def _age_hours(iso, at):
    try:
        moment = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
        return (at - moment).total_seconds() / 3600 if moment.tzinfo else None
    except (TypeError, ValueError):
        return None


def _has(text, pattern):
    return re.search(pattern, text or '', re.I) is not None


def _label(score):
    return 'Critical' if score >= 9 else 'High' if score >= 7 else 'Elevated' if score >= 5 else 'Moderate' if score >= 3 else 'Low'


# --- NWS alerts ---------------------------------------------------------------------------------------------

NWS_EVENTS = [  # first match wins; base score before adjustments
    (r'tornado emergency|flash flood emergency|extreme wind warning', 10, 'emergency-level warning'),
    (r'tornado warning', 9, 'tornado warning'),
    (r'evacuation immediate|civil danger|civil emergency|shelter in place|hazardous materials|nuclear power plant|radiological', 9, 'public-safety warning'),
    (r'flash flood warning', 8, 'flash flood warning'),
    (r'(excessive|extreme) heat warning|ice storm warning|blizzard warning|hurricane warning|fire warning|dust storm warning', 8, 'high-impact warning'),
    (r'severe thunderstorm warning|winter storm warning|flood warning|high wind warning|extreme cold warning|red flag warning|wind chill warning', 7, 'warning'),
    (r'warning', 6, 'warning'),
    (r'tornado watch', 6, 'tornado watch'),
    (r'watch', 5, 'watch'),
    (r'advisory', 4, 'advisory'),
    (r'statement|outlook|message', 3, 'statement'),
]


def _nws(item, reasons):
    name, a, text = item.get('name', ''), item.get('attributes') or {}, item.get('description') or ''
    score = 2
    for pattern, base, label in NWS_EVENTS:
        if _has(name, pattern):
            score = base
            reasons.append(f'NWS {label} ({name}): base {base}')
            break
    else:
        reasons.append(f'NWS product ({name}): base 2')
    for field, table in [('severity', {'extreme': 1, 'severe': 0.5, 'moderate': 0, 'minor': -1}),
                         ('urgency', {'immediate': 0.5, 'expected': 0, 'future': -1, 'past': -2}),
                         ('certainty', {'observed': 1, 'likely': 0.5, 'possible': -0.5, 'unlikely': -2})]:
        value = str(a.get(field) or '').lower()
        if value in table and table[value]:
            score += table[value]
            reasons.append(f'{field} {a[field]}: {table[value]:+g}')
    for pattern, points, why in [(r'particularly dangerous situation', 1, 'particularly dangerous situation'),
                                 (r'catastrophic', 1, 'catastrophic damage wording'),
                                 (r'destructive', 1, 'destructive damage wording'),
                                 (r'considerable', 0.5, 'considerable damage wording'),
                                 (r'life[- ]threatening', 0.5, 'life-threatening wording')]:
        if _has(text, pattern):
            score += points
            reasons.append(f'{why}: +{points:g}')
            break
    if _has(a.get('areaDesc'), r'\bdallas\b'):
        score += 0.5
        reasons.append('area includes Dallas: +0.5')
    return score


# --- Iowa Environmental Mesonet storm reports -----------------------------------------------------------------

def _iem(item, reasons, at):
    kind, a = item.get('name', '').upper(), item.get('attributes') or {}
    size = _num(a.get('magf')) if _num(a.get('magf')) is not None else _num(a.get('magnitude'))
    unit = str(a.get('unit') or '').upper()
    if 'TORNADO' in kind:
        score, why = 8, 'tornado report'
    elif 'FUNNEL' in kind or 'WATERSPOUT' in kind:
        score, why = 5, 'funnel cloud report'
    elif 'FLASH FLOOD' in kind:
        score, why = 7, 'flash flood report'
    elif 'FLOOD' in kind:
        score, why = 6, 'flood report'
    elif 'HAIL' in kind:
        score = 7 if size and size >= 2 else 5 if size and size >= 1 else 3
        why = f'hail {size:g} in' if size else 'hail report'
    elif 'WND' in kind or 'WIND' in kind:
        mph = size if size and unit in ('MPH', '') else size * 1.15078 if size and unit in ('KT', 'KNOTS') else None
        score = 7 if mph and mph >= 75 else 5 if mph and mph >= 58 else 4
        if 'DMG' in kind:
            score = max(score, 6)
        if 'NON-TSTM' in kind:
            score -= 1
        why = f'{kind.lower()}{f" {mph:.0f} mph" if mph else ""}'
    elif any(word in kind for word in ['ICE STORM', 'DEBRIS FLOW', 'LANDSLIDE', 'WILDFIRE', 'DUST STORM']):
        score, why = 6, kind.lower()
    elif any(word in kind for word in ['FREEZING RAIN', 'BLIZZARD', 'LIGHTNING']):
        score, why = 5, kind.lower()
    else:
        score, why = 3, f'{kind.lower() or "storm"} report'
    reasons.append(f'Storm report: {why}: base {score}')
    remark = a.get('remark') or ''
    for pattern, points, label in [(r'fatal|killed|\bdead\b|death', 2.5, 'deaths mentioned'),
                                   (r'trapped|water rescue|swift water|rescue', 2, 'rescue or people trapped'),
                                   (r'injur', 1.5, 'injuries mentioned'),
                                   (r'collapse|destroy|roof (?:off|removed)', 1.5, 'structural damage'),
                                   (r'road(?:s)? closed|impassable|stranded|stalled|cars? (?:in|under) water', 1, 'roads blocked or vehicles stranded'),
                                   (r'power lines? down|downed (?:power )?lines|outage', 0.5, 'power lines down')]:
        if _has(remark, pattern):
            score += points
            reasons.append(f'{label}: +{points:g}')
    age = _age_hours(item.get('observed_at'), at)
    if age is not None and age > 12:
        score -= 2
        reasons.append(f'reported {age:.0f} h ago: -2')
    elif age is not None and age > 6:
        score -= 1
        reasons.append(f'reported {age:.0f} h ago: -1')
    return score


# --- Dallas police calls ------------------------------------------------------------------------------------

POLICE_TYPES = [
    (r'active shooter|shooting|shots? fired|\bshoot', 2.5, 'shooting'),
    (r'hazmat|gas leak|explosion|bomb', 2, 'explosion, bomb or hazardous material'),
    (r'drown|water rescue|flood', 2, 'water emergency'),
    (r'stab|cutting|assault|aggravated', 1.5, 'violent assault'),
    (r'robbery|kidnap|hostage', 1.5, 'robbery or abduction'),
    (r'\bfire\b|burning', 1, 'fire'),
    (r'injur|ambulance|medical|unconscious', 1, 'injured person'),
    (r'major accident|\b7x', 1, 'major accident'),
    (r'missing|child|amber', 1, 'missing person or child'),
    (r'disturbance|fight|domestic', 0.5, 'disturbance'),
]


def _police(item, reasons, at):
    a = item.get('attributes') or {}
    priority = str(a.get('priority') or '').strip()
    score = {'1': 6, '2': 4.5, '3': 3, '4': 2}.get(priority, 3)
    reasons.append(f'Dallas police priority {priority or "unknown"} (1 is most urgent): base {score:g}')
    call = item.get('name', '')
    for pattern, points, label in POLICE_TYPES:
        if _has(call, pattern):
            score += points
            reasons.append(f'call type {label}: +{points:g}')
            break
    if _has(call, r'freeway|fwy|expy|hwy') or _has(a.get('location'), r'\b(fwy|expy|hwy|tollway|freeway)\b'):
        score += 0.5
        reasons.append('on a freeway: +0.5')
    if _has(a.get('status'), r'in progress') or _has(call, r'in progress'):
        score += 1
        reasons.append('in progress: +1')
    age = _age_hours(item.get('observed_at'), at)
    if age is not None and age > 3:
        score -= 1
        reasons.append(f'call open {age:.0f} h: -1')
    # A single police call is a local incident; leave 10 for regional emergencies.
    if score > 9:
        score = 9
        reasons.append('capped at 9 for a single police call')
    return score


# --- Wildfires and earthquakes --------------------------------------------------------------------------------

def _nifc(item, reasons):
    a = item.get('attributes') or {}
    score = 6
    reasons.append('Published wildfire perimeter: base 6')
    acres, contained = _num(a.get('poly_GISAcres')), _num(a.get('attr_PercentContained'))
    if acres is not None:
        points = 2 if acres >= 10000 else 1.5 if acres >= 1000 else 1 if acres >= 100 else -1 if acres < 10 else 0
        if points:
            score += points
            reasons.append(f'{acres:,.0f} acres: {points:+g}')
    if contained is not None:
        points = -2 if contained >= 90 else -1 if contained >= 50 else 0.5 if contained == 0 else 0
        if points:
            score += points
            reasons.append(f'{contained:g}% contained: {points:+g}')
    if str(a.get('attr_IncidentTypeCategory') or '').upper() == 'RX':
        score -= 3
        reasons.append('prescribed burn: -3')
    return score


def _earthquake(item, reasons):
    a = item.get('attributes') or {}
    magnitude = _num(a.get('magnitude'))
    if magnitude is None:
        reasons.append('earthquake without magnitude: base 3')
        score = 3
    else:
        score = 10 if magnitude >= 6 else 8 if magnitude >= 5 else 6 if magnitude >= 4 else 4 if magnitude >= 3 else 2 if magnitude >= 2.5 else 1
        reasons.append(f'magnitude {magnitude:.1f}: base {score}')
    alert = str(a.get('alert') or '').lower()
    points = {'red': 3, 'orange': 2, 'yellow': 1}.get(alert)
    if points:
        score += points
        reasons.append(f'USGS PAGER {alert} alert: +{points}')
    mmi = _num(a.get('mmi'))
    if mmi is not None and mmi >= 6:
        score += 1
        reasons.append(f'shaking intensity {mmi:.1f}: +1')
    felt = _num(a.get('felt'))
    if felt is not None and felt >= 100:
        score += 0.5
        reasons.append(f'{felt:.0f} felt reports: +0.5')
    depth = _num(a.get('depth_km'))
    if depth is not None and depth < 5 and magnitude and magnitude >= 3:
        score += 0.5
        reasons.append(f'shallow {depth:.1f} km: +0.5')
    if a.get('tsunami'):
        score += 1
        reasons.append('tsunami flag: +1')
    return score


def assess(item, at=None):
    """Return {'score', 'label', 'reasons', 'basis'} for alert/incident items, else None."""
    if item.get('kind') not in SCORED_KINDS:
        return None
    at = at or datetime.now(timezone.utc)
    reasons = []
    source = item.get('source')
    if source == 'nws_alerts':
        raw = _nws(item, reasons)
    elif source == 'iem':
        raw = _iem(item, reasons, at)
    elif source == 'dallas_police':
        raw = _police(item, reasons, at)
    elif source == 'nifc':
        raw = _nifc(item, reasons)
    elif source == 'earthquakes':
        raw = _earthquake(item, reasons)
    else:
        raw = 4
        reasons.append(f'{source} {item.get("kind")}: default 4')
    if item.get('latitude') is None:
        reasons.append('location unknown')
    score = max(1, min(10, int(raw + 0.5)))  # round half up, clamp to 1-10
    return {'score': score, 'label': _label(score), 'reasons': reasons, 'basis': VERSION}


GUIDELINES = """Priority scale: 1-10, 10 = most urgent danger to people. Labels: 9-10 Critical, 7-8 High, 5-6 Elevated, 3-4 Moderate, 1-2 Low.

NWS alerts. Base by event (first match): Tornado Emergency, Flash Flood Emergency, Extreme Wind Warning = 10. Tornado Warning = 9.
Evacuation Immediate, Civil Danger/Emergency, Shelter in Place, Hazardous Materials, Nuclear/Radiological = 9. Flash Flood Warning = 8.
Excessive/Extreme Heat, Ice Storm, Blizzard, Hurricane, Fire, Dust Storm Warning = 8. Severe Thunderstorm, Winter Storm, Flood,
High Wind, Extreme Cold, Red Flag, Wind Chill Warning = 7. Other warnings = 6. Tornado Watch = 6. Other watches = 5. Advisories = 4.
Statements, outlooks, messages = 3. Anything else = 2.
Adjust: severity Extreme +1, Severe +0.5, Minor -1. Urgency Immediate +0.5, Future -1, Past -2. Certainty Observed +1, Likely +0.5,
Possible -0.5, Unlikely -2. Text wording (first match): "particularly dangerous situation" +1, "catastrophic" +1, "destructive" +1,
"considerable" +0.5, "life-threatening" +0.5. Area includes Dallas +0.5.

Storm reports (preliminary). Base: tornado 8, funnel cloud 5, flash flood 7, flood 6, ice storm/debris flow/landslide/wildfire/dust
storm 6, freezing rain/blizzard/lightning 5, other 3. Hail >= 2 in = 7, >= 1 in = 5, smaller 3. Wind >= 75 mph = 7, >= 58 mph = 5,
else 4; damage reported at least 6; non-thunderstorm wind -1. Remarks: deaths +2.5, rescue/people trapped +2, injuries +1.5,
collapse/destroyed +1.5, roads closed/vehicles stranded +1, power lines down +0.5. Reported over 6 h ago -1, over 12 h ago -2.

Dallas police calls. Base from DPD priority (1 most urgent): 1 = 6, 2 = 4.5, 3 = 3, 4 = 2, missing = 3. Call type (first match):
shooting +2.5; explosion/bomb/hazmat +2; drowning/water rescue/flood +2; stabbing/assault +1.5; robbery/kidnapping/hostage +1.5;
fire +1; injury/medical +1; major accident +1; missing person/child +1; disturbance/fight/domestic +0.5. Freeway +0.5.
In progress +1. Open over 3 h -1. A single police call is capped at 9.

Wildfire perimeters. Base 6. Acres >= 10,000 +2, >= 1,000 +1.5, >= 100 +1, < 10 -1. Contained >= 90% -2, >= 50% -1, 0% +0.5.
Prescribed burn -3.

Earthquakes. Magnitude >= 6 = 10, >= 5 = 8, >= 4 = 6, >= 3 = 4, >= 2.5 = 2, else 1. USGS PAGER alert red +3, orange +2, yellow +1.
Shaking intensity (MMI) >= 6 +1. 100+ felt reports +0.5. Shallow (< 5 km) at magnitude >= 3 +0.5. Tsunami flag +1.

Round half up and clamp to 1-10."""


def enrich_priority(item, at=None):
    result = assess(item, at)
    return {**item, 'priority': result} if result else item
