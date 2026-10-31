"""Measurement layer: what each campaign round found, how it was decided, and what cleared.

Every mechanism in this runtime was added because a campaign went wrong, and none can be kept or
retired on evidence without a record of what the reviewers actually caught. `triage` appends a
line with each reviewer's findings by disposition, and `finish` appends the clearance;
`review_flow.py outcomes` reads them back. The log lives beside the campaign directories, in the
shared Git directory, so it survives campaigns, archives and worktrees.

review_flow imports this module, so nothing here imports review_flow.
"""
from collections import Counter
from datetime import datetime, timezone
import json

LOG = 'outcomes.jsonl'


def append(directory, kind, state):
    """Record one triaged round or one clearance of this campaign."""
    entry = dict(kind=kind, at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                 campaign=directory.name, head=state['head'], round=state.get('round', 1),
                 delivery_used=state.get('delivery_used'))
    if kind == 'triage':
        statuses = {item['id']: item['status'] for item in state.get('triage') or []}
        entry['reviewers'] = {
            name: dict(Counter(statuses.get(name + '::' + finding['id'], 'unknown')
                               for finding in report.get('findings', [])))
            for name, report in (state.get('reviews') or {}).items()}
    with (directory.parent / LOG).open('a') as log:
        log.write(json.dumps(entry, sort_keys=True) + '\n')


def summary(directory):
    """Per reviewer: findings raised and how they were decided; rounds to clear."""
    path = directory.parent / LOG
    entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    reviewers = {}
    for entry in (e for e in entries if e['kind'] == 'triage'):
        for name, counts in entry.get('reviewers', {}).items():
            reviewers.setdefault(name, Counter()).update(counts)
    cleared = [e for e in entries if e['kind'] == 'cleared']
    rounds = Counter(e['round'] for e in cleared)
    return dict(log=str(path), triaged_rounds=sum(1 for e in entries if e['kind'] == 'triage'),
                cleared_candidates=len(cleared), rounds_to_clear=dict(sorted(rounds.items())),
                reviewers={name: dict(counts) for name, counts in sorted(reviewers.items())})
