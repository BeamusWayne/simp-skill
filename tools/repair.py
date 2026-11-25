#!/usr/bin/env python3
"""Choose a communication step from facts supplied by the host."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sys
from typing import Literal, get_args


Goal = Literal['listen', 'understand', 'draft', 'review', 'pursue']
Situation = Literal[
    'ordinary', 'ambiguous', 'user_hurt', 'user_harmed_other', 'mutual_conflict', 'external_hurt'
]
Contact = Literal['open', 'no_contact', 'pause', 'unsafe', 'uncertain']
IssueStatus = Literal['open', 'discussed', 'resolved', 'closed_by_user', 'needs_review']
Action = Literal[
    'respond_normally', 'listen', 'clarify', 'offer_opening', 'offer_support',
    'plan_return', 'respect_boundary', 'review_evidence',
]


def require_timezone(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f'{name} must be a datetime with a timezone')


@dataclass(frozen=True)
class RepairContext:
    goal: Goal
    situation: Situation
    contact: Contact = 'open'
    issue_status: IssueStatus | None = None
    heated: bool = False
    romance_declined: bool = False
    revisit_at: datetime | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for key, options in (
            ('goal', get_args(Goal)), ('situation', get_args(Situation)),
            ('contact', get_args(Contact)), ('issue_status', (*get_args(IssueStatus), None)),
        ):
            if getattr(self, key) not in options:
                raise ValueError(f'invalid {key}')
        if type(self.heated) is not bool or type(self.romance_declined) is not bool:
            raise ValueError('heated and romance_declined must be booleans')
        if not isinstance(self.evidence_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip() for ref in self.evidence_refs
        ):
            raise ValueError('evidence_refs must contain nonempty strings')
        if self.revisit_at is not None:
            require_timezone(self.revisit_at, 'revisit_at')
            if self.contact != 'pause':
                raise ValueError('revisit_at requires a paused conversation')


@dataclass(frozen=True)
class RepairPlan:
    action: Action
    reason: str
    evidence_refs: tuple[str, ...]
    avoid_romantic_pursuit: bool
    revisit_at: datetime | None = None


def plan_repair(context: RepairContext, *, now: datetime) -> RepairPlan:
    """Apply contact limits before suggesting any action and keep timing advisory."""
    require_timezone(now, 'now')

    def plan(action: Action, reason: str, revisit_at: datetime | None = None) -> RepairPlan:
        return RepairPlan(action, reason, context.evidence_refs, context.romance_declined, revisit_at)

    if context.contact == 'unsafe':
        return plan('respect_boundary', 'unsafe_contact')
    if context.contact == 'no_contact':
        return plan('respect_boundary', 'contact_declined')
    if context.goal == 'pursue' and context.romance_declined:
        return plan('respect_boundary', 'romance_declined')
    if context.goal == 'listen':
        return plan('listen', 'user_wants_to_be_heard')
    if context.contact == 'uncertain':
        return plan('clarify', 'contact_boundary_uncertain')
    if context.contact == 'pause':
        if context.revisit_at is None:
            return plan('respect_boundary', 'requested_space')
        if context.revisit_at > now:
            return plan('plan_return', 'agreed_return_pending', context.revisit_at)
        return plan('clarify', 'agreed_return_due', context.revisit_at)
    if context.issue_status == 'needs_review':
        return plan('clarify', 'issue_evidence_corrected')
    if context.issue_status in ('resolved', 'closed_by_user'):
        action = 'review_evidence' if context.goal == 'review' else 'respond_normally'
        return plan(action, 'issue_closed')
    if context.situation == 'ordinary':
        return plan('respond_normally', 'no_known_conflict')
    if context.situation == 'ambiguous':
        return plan('clarify', 'no_concrete_event')
    if context.goal in ('understand', 'review'):
        return plan('review_evidence', context.situation)
    if context.situation == 'external_hurt':
        return plan('offer_support', 'external_hurt')
    if context.heated:
        return plan('plan_return', 'needs_deescalation')
    return plan('offer_opening', context.situation)


def read_context() -> RepairContext:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError('repair context must be a JSON object')
    if 'evidence_refs' in payload:
        if not isinstance(payload['evidence_refs'], list):
            raise ValueError('evidence_refs must be an array')
        payload['evidence_refs'] = tuple(payload['evidence_refs'])
    if payload.get('revisit_at') is not None:
        payload['revisit_at'] = datetime.fromisoformat(payload['revisit_at'])
    return RepairContext(**payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan'], help='read a JSON context from stdin')
    parser.add_argument('--now', help='timezone-aware ISO 8601 time for reproducible decisions')
    args = parser.parse_args()
    try:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
        result = plan_repair(read_context(), now=now)
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    payload = asdict(result)
    payload['revisit_at'] = result.revisit_at.isoformat() if result.revisit_at is not None else None
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == '__main__':
    main()
