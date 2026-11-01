"""Rebase layer: the campaign a candidate continues as after its branch is rebased onto a moved base.

A rebase rewrites every commit, so the frozen head stops being an ancestor of the new one and the
ordinary rounds refuse it. What the reviewers read was a delta, not a commit id. When the rebased
delta against the new base is the delta they read and that candidate cleared, their
reports still describe it, and only the declared gates run again on the new tree. When the rebase changed the delta (a
conflict resolved, a commit dropped or added), the new delta is unreviewed and opens a round that
reviews it in full from the new base.

review_flow imports this module, so nothing here imports review_flow.
"""
import subprocess

from review_git import git, require

# What a rebind keeps of the candidate it continues: everything its reviewers and its author
# recorded about the delta, which is unchanged.
KEPT = ('round', 'reviews', 'triage', 'previous_triage', 'retrospectives', 'answers', 'widen_scope',
        'nit_round', 'after_archived', 'design_round', 'reopened', 'codex_waiver', 'claude_waiver',
        'prose', 'regression_measured')


def delta_id(base, head):
    """An id of the change base..head that identical deltas share, whatever commits carry them.

    `--verbatim` keeps whitespace, which the default patch-id normalises away.
    """
    diff = subprocess.run(['git', 'diff', '--no-ext-diff', '--no-renames', '--binary', '--full-index',
                           base, head], capture_output=True, check=True).stdout
    ids = subprocess.run(['git', 'patch-id', '--verbatim'], input=diff, capture_output=True,
                         check=True).stdout.split()
    return ids[0].decode() if ids else ''


def checked(args, old, head, base):
    """Refuse a --rebased-from that does not describe a rebase of the frozen candidate."""
    require(old is not None, 'Nothing to continue: no campaign is frozen on this branch.')
    previous = git('rev-parse', '--verify', args.rebased_from + '^{commit}')
    require(previous == old['head'], '--rebased-from names ' + previous[:12] + ', and this campaign froze '
            + old['head'][:12] + '. Name the head the campaign froze.')
    require(git('merge-base', old['head'], head) != old['head'],
            'The candidate descends from the frozen head, so it is a correction, not a rebase. '
            'Drop --rebased-from.')
    require(git('merge-base', old['base'], base) == old['base'],
            'The new base does not contain the old one. A rebase moves the branch onto a later '
            'commit of the branch it merges into.')


def rebased(args, old, head, base, branch):
    """The state a rebased candidate continues from: a rebind when the delta is unchanged and the
    frozen candidate had cleared, otherwise the next round, reviewing the new delta in full."""
    checked(args, old, head, base)
    before, after = delta_id(old['base'], old['head']), delta_id(base, head)
    require(before and after, 'An empty delta has nothing to review.')
    same = before == after and bool(old.get('cleared'))
    record = dict(from_head=old['head'], from_base=old['base'], delta=after, same_delta=same)
    if same:
        state = {key: old[key] for key in KEPT if key in old}
        state.update(head=head, review_base=base, base_branch=branch, rebased=record)
        # Claude quota evidence names the candidate it was measured on, and the carried reviews
        # are that delta's, so it moves to the rebased head; its date, binary and round are kept
        # and still checked as before.
        waiver = old.get('claude_waiver')
        if isinstance(waiver, dict) and waiver.get('head') == old['head']:
            state['claude_waiver'] = dict(waiver, head=head)
        return state
    return dict(head=head, review_base=base, base_branch=branch, round=old['round'] + 1,
                previous_triage=old.get('triage') or [], retrospectives=old.get('retrospectives', []),
                nit_round='', widen_scope='', answers=[], after_archived='', rebased=record)


def carried(state):
    """What a rebind restores after start resets a new candidate's reviews and dispositions."""
    if not (state.get('rebased') or {}).get('same_delta'):
        return {}
    return {key: state[key] for key in ('reviews', 'triage') if key in state}
