#!/usr/bin/env python3
"""Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.

Git supplies the SHAs being pushed on stdin, one "local_ref local_sha remote_ref
remote_sha" line per ref. Nothing here reads the command line that produced the
push, so no spelling of that command line can reach a remote without a receipt.
This file is copied into the repository's hooks directory by review_flow.py and
must stay self-contained: it imports only the standard library.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# Must equal review_flow.POLICY: this file is copied into hooks directories on its own
# and cannot import it. test_review_prepush asserts the two agree.
POLICY = 2
DELETION = '0' * 40


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


def orphaned(state):
    """A probe receipt names the process holding it; one whose process is gone is void."""
    pid = state.get('probe_pid')
    if pid is None:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return True
    except PermissionError:  # another user's live process
        return False
    except (TypeError, ValueError, OverflowError):  # not a pid at all: nothing holds it
        return True
    return False


def cleared(common, sha):
    """Report whether a completed Claude + Codex campaign cleared exactly this commit."""
    for path in receipts(common):
        try:
            state = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (state.get('head') == sha and state.get('cleared')
                and state.get('policy') == POLICY
                and set(state.get('reviews', {})) == {'claude', 'codex'}
                and not orphaned(state)):
            return True
    return False


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
        if not cleared(common, peeled(local_sha)):
            print(f'pre-push: no completed Claude + Codex review for {local_sha[:12]} '
                  f'({local_ref} -> {remote_ref}). Run /bymax-quality:code-review and finish '
                  'the campaign; a receipt is required for every pushed commit.', file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
