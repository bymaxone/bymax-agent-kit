"""Replacement layer: the candidate a fixed head becomes when a gate of the frozen one
failed before any reviewer read it, kept in the same round, and the scope refusal a correction
and a replacement both raise.

review_flow imports this module, so nothing here imports review_flow: how a correction's
evidence and its widened files are measured is the runtime's, and `replacement` is handed those
two measures by its caller.
"""
from review_delivery import scope_of as scope
from review_git import git, require

# What a replacement keeps of the candidate it replaces: the round and everything it was told.
KEPT = ('round', 'review_base', 'previous_triage', 'retrospectives', 'answers', 'widen_scope',
        'nit_round', 'after_archived', 'design_round', 'reopened')


def within_scope(extra, reason):
    """Refuse a correction touching files no open finding names, unless a reason was recorded."""
    require(not extra or reason,
            'A correction round answers the open findings and nothing else. No open finding '
            'names: ' + ', '.join(extra) + '. Revert what they do not name and file it as its '
            'own campaign, or record why this round must widen with --widen-scope "<why>"; '
            'both reviewers are told, and they will review the wider delta.')


def failed_checks(state):
    """The latest run of each gate recorded on this candidate that did not exit 0, as (command,
    exit status), in command order.

    prompt() refuses a candidate with any of them and replaceable() takes the same set, so a
    candidate no reviewer may read can always be replaced: a run that timed out or was
    interrupted has no exit status and counts, and so does a command the context did not name."""
    latest = {tuple(c['command']): c['exit_code'] for c in state.get('checks') or []}
    return sorted((command, code) for command, code in latest.items() if code != 0)


def replaceable(old):
    """Whether a new head replaces this candidate within its round instead of opening the next.

    prompt() refuses a candidate a gate failed on, so no reviewer can read it and the
    round would never advance past it: the fixed commit takes its place. Once a reviewer has read
    a candidate that reading is spent on it, and a cleared candidate is answered by a correction.
    An adapter reserves its attempt before the model reads and records the report after, so an
    attempt spent or still running counts as a reading as much as a report does.
    """
    return (bool(old) and not old.get('cleared') and not old.get('reviews') and not read(old)
            and bool(failed_checks(old)))


def read(state):
    """Whether a reviewer attempt was reserved on this candidate, finished or not: each adapter
    counts it under `<reviewer>_attempts` as it launches the model."""
    return any(count for name, count in state.items() if name.endswith('_attempts'))


def replacement(args, old, head, base, context, branch, *, evidence, widened):
    """The candidate that replaces one its own gate failed, in the same round.

    What belonged to the failed head — its checks, its reviews, its triage — is not kept, and
    the replaced head is listed so the history stays visible. The delta reviewers read starts at
    the review base, so the new head descends from it: an amend of the failed candidate does,
    unrelated history does not. `evidence` and `widened` are review_flow's correction_evidence
    and widened, which a correction round's replacement is measured by.
    """
    require(old['base'] == base and scope(old['context']) == scope(context),
            'Scope changed. Stop and agree on a separate campaign.')
    review_base = old['review_base']
    require(git('merge-base', review_base, head) == review_base,
            'This candidate does not descend from ' + review_base[:12] + ', the review base of the '
            'candidate whose gate failed. A replacement fixes that candidate; history that does '
            'not reach its review base has no delta to review.')
    kept = old.get('answers') or []
    require(not args.answers or list(args.answers) == kept,
            'A replacement keeps the answers its round was started with ('
            + (', '.join(kept) or 'none') + '); name those, or none.')
    state = {name: old[name] for name in KEPT if name in old}
    state.update(head=head, base_branch=branch, replaced=old.get('replaced', []) + [old['head']])
    if old['round'] > 1:
        state.update(replaced_correction(args, old, head, branch, evidence, widened))
    return state


def replaced_correction(args, old, head, branch, evidence, widened):
    """A replacement's correction contract, measured as the failed candidate's was: from the
    review base, against the findings its round answers. The design decision is kept, since
    the triages it was read from have not changed."""
    predecessor = dict(old, head=old['review_base'], triage=old['previous_triage'])
    measured = evidence(args, predecessor, head, branch)
    widen = old.get('widen_scope') or args.widen_scope
    within_scope(widened(predecessor, head, old.get('answers') or ()), widen)
    return dict(measured, widen_scope=widen)
