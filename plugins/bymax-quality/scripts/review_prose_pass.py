"""The prose pass as the campaign runs it: hand a committed candidate's prose to a fresh
reader, check what the reader left against review_prose's envelope, record it, and hold
start() to a record bound to the candidate's own text.

Runtime layer, between review_flow's CLI and review_prose's envelope. It never writes to the
working tree: what the reader left stays where it is, and a refusal only says so.
"""
import json
import os
import subprocess

import review_claims
from review_git import FOR_A_READER, clean_head, git, git_raw, require


PROSE_TOOLS = 'Read,Grep,Glob,Edit'


def prose_command(root):
    """A fresh Claude allowed to edit and nothing else; the envelope decides what it edited.

    The same hardening as the reviewer pass — no hooks, no MCP, no slash commands, no session
    — plus Edit under acceptEdits, because a pass that can only report is the round this
    exists to remove. What it may edit is not a permission question: review_prose.offences
    reads the tree afterwards and an edit outside the envelope refuses the whole pass.
    """
    return ['claude', '-p', '--output-format', 'json', '--tools', PROSE_TOOLS,
            '--allowedTools', PROSE_TOOLS, '--permission-mode', 'acceptEdits', '--add-dir', root,
            '--disable-slash-commands', '--no-session-persistence', '--max-turns', '40',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--settings', '{"disableAllHooks":true}']


def prose_run(args, directory, base_of):
    """Run the prose pass on a committed candidate that is not yet frozen, and record what it left.

    Three stages, because a Claude cannot start another Claude: `run` does everything with
    the CLI; inside a Claude session, `prepare` prints the task for a fresh subagent with
    Edit and leaves a marker saying it began on a clean tree, and `verify` requires that
    marker. The marker proves the tree was clean when the task was handed out; the runtime
    does not observe who edited between the stages. The record binds to the text the pass
    left, and start() recomputes its digest on the candidate. `base_of(args, directory, head)`
    is the campaign's answer to where the delta starts.
    """
    import review_prose
    directory.mkdir(parents=True, exist_ok=True)
    if args.stage == 'verify':
        head = git('rev-parse', 'HEAD')
        where = directory / ('prose-' + head + '.json')
        kept = json.loads(where.read_text()) if where.exists() else {}
        require(kept.get('outcome') == 'prepared', 'Nothing was prepared at this head. Run `prose '
                '--stage prepare` on a clean tree first: its marker proves the tree was clean when '
                'the task was handed out, which is what binds the record to a pass at all.')
        # None, not an empty set: a marker without a snapshot compares nothing, and an empty
        # one would make every ignored file that predates the pass a new one.
        return prose_verify(kept['base'], head, directory, kept.get('ignored'))
    head = clean_head()
    base = base_of(args, directory, head)
    where = directory / ('prose-' + head + '.json')
    task = review_prose.prepare(base, head)
    if not task:
        record = dict(base=base, head=head, files=[], digest=None, cut=0, changed=[],
                      outcome='skipped', why='this delta added no prose')
        where.write_text(json.dumps(record, indent=2) + '\n')
        return record
    if args.stage == 'prepare':
        # The ignored files present now: one the reader creates is a file it left, and a set
        # the listing must not refuse — ignored files never reach a candidate.
        where.write_text(json.dumps(dict(base=base, head=head, outcome='prepared',
                                         ignored=review_prose.ignored()), indent=2) + '\n')
        print(task)
        return None
    require(not os.environ.get('CLAUDECODE'), 'Inside Claude, a Claude cannot be started: '
            'run `prose --stage prepare`, hand the task to a fresh subagent with Edit, then '
            'run `prose --stage verify`.')
    before = review_prose.ignored()
    read_with(task, directory / ('prose-' + head + '.log'))
    return prose_verify(base, head, directory, before)


LEFT = ('The tree holds exactly what the reader left; nothing was put back. The runtime never writes '
        'to the tree, because no listing git offers proves what in it is the author\'s — hidden '
        'untracked files, assume-unchanged edits and ignored submodules all pass as clean to one, '
        'and a restore to HEAD destroys them. Inspect `git status`, put back what you need, and run '
        'the pass again; prepare and start refuse a dirty tree until then.')


def read_with(task, log):
    """Run the reader. A reader that failed or timed out leaves its edits where they are."""
    try:
        with log.open('w') as out:
            done = subprocess.run(prose_command(git('rev-parse', '--show-toplevel')), input=task,
                                  **FOR_A_READER, stdout=out, stderr=subprocess.STDOUT, timeout=900)
    except subprocess.TimeoutExpired:
        raise ValueError('The prose pass timed out; inspect ' + str(log) + '. ' + LEFT) from None
    require(done.returncode == 0, 'The prose pass failed; inspect ' + str(log) + '. ' + LEFT)


def prose_verify(base, head, directory, ignored_before=None):
    """Check what the pass left: record it if it stayed inside the envelope, refuse it if not.

    A refusal touches nothing: an empty git listing does not prove the tree equals HEAD, so
    any automatic revert can destroy work a listing hides, and the author, who can see what
    is theirs, puts the tree back.
    """
    import review_matrix
    import review_prose
    root = git('rev-parse', '--show-toplevel')
    broken = review_prose.offences(ignored_before=ignored_before)
    if broken:
        raise ValueError('The pass left the envelope:\n  ' + '\n  '.join(broken) + '\n' + LEFT)
    changed = review_prose.changed()
    files = bound(base, head)
    record = dict(base=base, head=head, files=files, digest=review_matrix.digest(root, files),
                  cut=review_prose.cut(), changed=changed,
                  outcome='corrected' if changed else 'unchanged')
    (directory / ('prose-' + head + '.json')).write_text(json.dumps(record, indent=2) + '\n')
    return record


def bound(base, head):
    """The touched files the candidate still has. Without renames a deletion, and a rename's
    old side, are touched paths with no bytes to digest and no prose to bind."""
    kept = set(git_raw('diff', '--name-only', '--no-renames', '-z', '--diff-filter=d', base, head).split('\0'))
    return [name for name in review_claims.touched(base, head) if name in kept]


def prose_first(state, directory):
    """A candidate whose delta added prose carries the record of the pass that read it.

    Bound by content, not by head: the record is written before the commit that carries the
    corrections, so it cannot know the candidate's head. It names the files and their digest
    after the pass; the candidate must digest the same, or its prose is not what was read.
    """
    base, head = state['review_base'], state['head']
    if not review_claims.added(base, head):
        return
    import review_matrix
    root = git('rev-parse', '--show-toplevel')
    for path in sorted(directory.glob('prose-*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        kept = json.loads(path.read_text())
        if kept.get('base') != base or kept.get('outcome') == 'skipped' or not kept.get('files'):
            continue
        # The candidate's own set, not the pass's: a record over the files the pass saw says
        # nothing about a file committed afterwards, whose prose would reach reviewers under a
        # note saying a reader had seen it.
        if set(kept['files']) != set(bound(base, head)):
            continue
        if review_matrix.digest(root, kept['files']) == kept.get('digest'):
            state['prose'] = dict(record=path.name, files=len(kept['files']), cut=kept['cut'],
                                  outcome=kept['outcome'])
            return
    require(False, 'This delta adds prose and no prose pass read it on this text, in these files. Run '
            '`review_flow.py prose --base %s` on the committed candidate, commit what it corrected, '
            'then start. A record bound to other text does not count: the pass binds to what it '
            'left, and a candidate whose prose is anything else was not read.' % base[:12])


def prose_note(state):
    """What the logic reviewers are told about prose: that it was read, and that it is not theirs."""
    if not review_claims.added(state['review_base'], state['head']):
        return 'This delta added no prose, so no prose pass ran and nothing here is a wording question.'
    kept = state.get('prose')
    if not kept:
        return ('This delta adds prose and carries no prose-pass record; it was frozen before the '
                'pass existed. Read its prose as you would any claim.')
    return ('The prose pass ran before the freeze: %d file(s) bound, %d line(s) of prose cut, '
            'none added, and the text you were handed digests to what it left (%s). The runtime '
            'does not observe the reader, so the record proves the text and not the reading. '
            'Wording is still not yours to review: a finding whose remedy is rewriting '
            'a comment, a docstring or a paragraph is not a finding here — unless the sentence '
            'states something FALSE about the code that a reader would act on, which is a '
            'correctness defect; file it with the code line that contradicts it.'
            % (kept['files'], kept['cut'], kept['record']))
