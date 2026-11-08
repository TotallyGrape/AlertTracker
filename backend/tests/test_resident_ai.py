import json
import pytest
from app.resident_ai import validate

JOB = {'name': 'Need help leaving', 'description': 'Water is entering the home. We need help leaving.', 'help_type': 'evacuation', 'people_affected': 2}


def reply(**extra):
    return json.dumps({'summary': 'Resident reports water entering the home and needs help leaving.',
                       'urgency': 'high', 'reasons': ['Reported water entering the home.'], 'evidence': 'Water is entering the home', **extra})


def test_supported_assessment_is_accepted():
    assert validate(reply(), JOB)['urgency'] == 'high'


@pytest.mark.parametrize('extra', [
    {'evidence': 'People are trapped on the roof'}, {'evidence': ''}, {'urgency': 'verified'},
    {'summary': 'There are 12 people trapped.'}, {'summary': '<script>bad</script>'},
    {'reasons': []}, {'summary': 'Go to https://example.test'},
])
def test_unsupported_or_malformed_assessment_is_rejected(extra):
    with pytest.raises(ValueError):
        validate(reply(**extra), JOB)
