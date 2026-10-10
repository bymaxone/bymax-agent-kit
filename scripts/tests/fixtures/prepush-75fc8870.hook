#!/usr/bin/env python3
"""Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.

Git supplies the SHAs being pushed on stdin, one "local_ref local_sha remote_ref
remote_sha" line per ref. Nothing here reads the command line that produced the
push, so no spelling of that command line can reach a remote without a receipt.
This file is copied into the repository's hooks directory by review_flow.py and
must stay self-contained: it imports only the standard library.

It also holds the one definition of which reviewers a receipt must carry, because that
question is asked in three places — here, in review_flow.py when a candidate clears, and
in review_push.py before the command runs — and three answers would be three policies.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

# Must equal review_flow.POLICY: this file is copied into hooks directories on its own
# and cannot import it. test_review_prepush asserts the two agree.
POLICY = 2
DELETION = '0' * 40

# A Codex the runtime could not run is waived, and the waiver is re-checked here rather
# than trusted: it is evidence about a machine, and this is the machine, now.
WAIVER_TTL = 24 * 3600
WAIVER_REASONS = ('absent', 'quota')

# Where a Codex CLI actually lands, per install channel. Read in this order and before
# $PATH: a receipt claiming Codex is absent must be wrong whenever it is installed
# normally, however the environment of one command was spelled.
CODEX_LOCATIONS = ('/opt/homebrew/bin/codex', '/usr/local/bin/codex', '/opt/local/bin/codex',
                   '/usr/bin/codex', '~/.local/bin/codex', '~/.bun/bin/codex',
                   '~/.volta/bin/codex', '~/.npm-global/bin/codex', '~/.nvm/current/bin/codex')


def resolve_codex():
    """The installed Codex CLI's absolute path, or None, found without trusting $PATH.

    $PATH is consulted last and only as a fallback for an unusual prefix, so a `codex`
    placed ahead of the real one cannot be the binary a waiver is measured against.

    The path is made absolute but never dereferenced. Every install channel here puts a
    stable name in front of a versioned file, so following the symlink would pin a waiver
    to a release and let a routine upgrade inside the window void a receipt that already
    cleared. Following it buys nothing either: both sides of the comparison call this same
    function, and whoever can move the symlink can move what runs.
    """
    for location in CODEX_LOCATIONS:
        candidate = Path(location).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return os.path.abspath(candidate)
    found = shutil.which('codex')
    return os.path.abspath(found) if found else None


def waiver_ok(waiver, now=None):
    """Whether a recorded Codex waiver still describes this machine.

    The runtime writes a waiver from its own probe; nothing the caller passes can create
    one. Honouring it is still conditional, because the probe ran earlier and elsewhere:
    an `absent` waiver is void the moment Codex is installed, a `quota` one is void unless
    the binary it names is still the one this machine resolves, and both expire. A waiver
    dated in the future is not evidence about anything and is void as well.
    """
    if not isinstance(waiver, dict) or waiver.get('reason') not in WAIVER_REASONS:
        return False
    at, now = waiver.get('at'), now if now is not None else time.time()
    if not isinstance(at, (int, float)) or isinstance(at, bool):
        return False
    if at > now + 60 or now - at > WAIVER_TTL:
        return False
    installed = resolve_codex()
    if waiver['reason'] == 'absent':
        return installed is None
    return installed is not None and waiver.get('binary') == installed


def reviewers_needed(state):
    """The reviewers this candidate's receipt must carry.

    The pair, unless the runtime's own probe found no Codex to run: then an independent
    second Claude pass stands in its place, so a receipt still rests on two readings of
    the diff by reviewers that never saw each other's findings.
    """
    return {'claude', 'claude-b'} if waiver_ok(state.get('codex_waiver')) else {'claude', 'codex'}


def satisfied(state):
    """Whether the recorded reviews are the ones this candidate needed."""
    return reviewers_needed(state) <= set(state.get('reviews') or {})


def explain(state):
    """Why a receipt's reviews fall short, in the terms the caller has to act on."""
    recorded = sorted(state.get('reviews') or {})
    waiver = state.get('codex_waiver')
    if waiver and not waiver_ok(waiver):
        installed = resolve_codex()
        if waiver.get('reason') == 'absent' and installed:
            return (f"its Codex waiver says Codex is not installed, but it is, at {installed}. "
                    'Run the campaign round again and let Codex review this candidate.')
        if waiver.get('reason') == 'quota' and installed != waiver.get('binary'):
            return (f"its Codex waiver was measured against {waiver.get('binary') or 'no binary'} and this "
                    f"machine resolves {installed or 'none'}. Run the round again against the installed Codex.")
        return ('its Codex waiver is not dated inside the window a waiver is evidence for; run the '
                'campaign round again so a reviewer sees this candidate.')
    return f"it carries {recorded or ['no reviews']} and needs {sorted(reviewers_needed(state))}"


def common_dir():
    """Resolve the shared Git directory, where receipts live for every worktree."""
    output = subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], text=True)
    return Path(output.strip()).resolve()


def receipts(common):
    """Yield every campaign state file, current and archived."""
    root = common / 'bymax-review'
    yield from root.glob('*/state.json')
    yield from root.glob('*/completed-*.json')


def peeled(sha):
    """The commit a pushed object resolves to: an annotated tag's SHA is the tag, not its commit."""
    result = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', sha + '^{commit}'],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else sha


def orphaned(path, state):
    """A probe receipt is valid only while its probe holds the lock on the holder file.

    The kernel releases the lock with the process, so a receipt left by a killed probe
    names a commit nobody can push, whatever pid the system reuses afterwards.
    """
    if 'probe_lock' not in state:
        return 'probe_pid' in state  # a probe receipt with nothing to hold is void
    name = state['probe_lock']
    try:
        with (path.parent / str(name)).open('r') as holder:
            fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:  # the probe is alive and holding it
        return False
    except OSError:  # no holder file at all: nothing holds the receipt
        return True
    return True


def cleared(common, sha):
    """Report whether a completed campaign cleared exactly this commit, and why not."""
    reason = ''
    for path in receipts(common):
        try:
            state = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (state.get('head') != sha or not state.get('cleared')
                or state.get('policy') != POLICY or orphaned(path, state)):
            continue
        if satisfied(state):
            return True, ''
        reason = explain(state)
    return False, reason


def main():
    """Fail closed on the first pushed commit without a receipt; allow ref deletions."""
    common = common_dir()
    for line in sys.stdin:
        fields = line.split()
        if len(fields) != 4:
            continue
        local_ref, local_sha, remote_ref, _ = fields
        if local_sha == DELETION:
            continue
        passed, reason = cleared(common, peeled(local_sha))
        if not passed:
            detail = ('a receipt for it is not usable: ' + reason) if reason else 'no completed review'
            print(f'pre-push: {local_sha[:12]} ({local_ref} -> {remote_ref}) cannot be pushed: {detail}. '
                  'Run /bymax-quality:code-review and finish the campaign; a receipt is required for '
                  'every pushed commit.', file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
