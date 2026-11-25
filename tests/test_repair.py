from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.repair import RepairContext, plan_repair


NOW = datetime.fromisoformat('2026-11-25T21:00:00+08:00')
SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'repair.py'


def test_refusal_of_contact_applies_to_an_ordinary_reply():
    context = RepairContext(
        goal='draft', situation='ordinary', contact='no_contact', evidence_refs=('turn:1',)
    )
    plan = plan_repair(context, now=NOW)
    assert plan.action == 'respect_boundary'
    assert plan.reason == 'contact_declined'
    assert plan.evidence_refs == ('turn:1',)


@pytest.mark.parametrize(('situation', 'action'), [
    ('ordinary', 'respond_normally'),
    ('ambiguous', 'clarify'),
    ('user_hurt', 'offer_opening'),
    ('user_harmed_other', 'offer_opening'),
    ('mutual_conflict', 'offer_opening'),
    ('external_hurt', 'offer_support'),
])
def test_next_step_depends_on_what_happened(situation, action):
    plan = plan_repair(RepairContext(goal='draft', situation=situation), now=NOW)
    assert plan.action == action


@pytest.mark.parametrize(('options', 'action', 'reason'), [
    ({'goal': 'listen', 'heated': True}, 'listen', 'user_wants_to_be_heard'),
    ({'heated': True}, 'plan_return', 'needs_deescalation'),
    ({'contact': 'pause'}, 'respect_boundary', 'requested_space'),
    ({'contact': 'unsafe'}, 'respect_boundary', 'unsafe_contact'),
    ({'contact': 'uncertain'}, 'clarify', 'contact_boundary_uncertain'),
    ({'issue_status': 'needs_review'}, 'clarify', 'issue_evidence_corrected'),
    ({'issue_status': 'resolved'}, 'respond_normally', 'issue_closed'),
    ({'issue_status': 'closed_by_user'}, 'respond_normally', 'issue_closed'),
    ({'issue_status': 'discussed'}, 'offer_opening', 'user_hurt'),
    ({'goal': 'review'}, 'review_evidence', 'user_hurt'),
])
def test_uses_current_goal_and_confirmed_status(options, action, reason):
    context = RepairContext(**({'goal': 'draft', 'situation': 'user_hurt'} | options))
    plan = plan_repair(context, now=NOW)
    assert (plan.action, plan.reason) == (action, reason)


def test_an_agreed_return_time_does_not_create_permission():
    context = RepairContext(goal='draft', situation='user_hurt', contact='pause', revisit_at=NOW)
    early = plan_repair(context, now=NOW.replace(hour=20))
    due = plan_repair(context, now=NOW)
    assert (early.action, early.reason, early.revisit_at) == ('plan_return', 'agreed_return_pending', NOW)
    assert (due.action, due.reason) == ('clarify', 'agreed_return_due')


def test_romantic_rejection_allows_a_non_romantic_goal_when_contact_is_open():
    constraint = {'situation': 'user_hurt', 'romance_declined': True}
    assert plan_repair(RepairContext(goal='pursue', **constraint), now=NOW).action == 'respect_boundary'
    plan = plan_repair(RepairContext(goal='draft', **constraint), now=NOW)
    assert plan.action == 'offer_opening'
    assert plan.avoid_romantic_pursuit is True


def test_cli_emits_the_plan_and_rejects_unzoned_return_time():
    payload = {
        'goal': 'draft', 'situation': 'user_hurt', 'contact': 'pause',
        'revisit_at': '2026-11-26T20:00:00+08:00', 'evidence_refs': ['turn:2'],
    }
    command = [sys.executable, str(SCRIPT), 'plan', '--now', NOW.isoformat()]

    def invoke(data):
        return subprocess.run(command, input=json.dumps(data), capture_output=True, encoding='utf-8')

    result = invoke(payload)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        'action': 'plan_return', 'reason': 'agreed_return_pending', 'evidence_refs': ['turn:2'],
        'revisit_at': '2026-11-26T20:00:00+08:00', 'avoid_romantic_pursuit': False,
    }
    invalid = invoke(payload | {'revisit_at': '2026-11-26T20:00:00'})
    assert invalid.returncode == 2
    assert 'timezone' in invalid.stderr
