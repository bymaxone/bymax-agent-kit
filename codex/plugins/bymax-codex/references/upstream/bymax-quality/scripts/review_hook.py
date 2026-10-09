#!/usr/bin/env python3
"""Hook layer: install the pre-push receipt check in a repository, and probe a kept hook until
it has shown it enforces receipts.

The hook itself is review_prepush.py, copied into the hooks directory; this module decides
whether to write it, replace an earlier release's copy, or keep a hook somebody else arranged,
and runs the probe pushes that a kept hook must answer as the bundled one would. The runtime
calls install_hook from `start`; nothing here reads or writes campaign state.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from review_git import git, require
# The policy a receipt is written under is the hook's own: review_prepush is self-contained and
# cannot import the runtime, and test_review_prepush asserts the runtime declares the same one.
from review_prepush import POLICY, WAIVER_TTL, resolve_claude, resolve_codex


HOOK_MARKER = 'Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.'

# sha256 of every bundled hook a previous release installed. The hook carries the receipt
# rule, so shipping a change to that rule means replacing the copy git actually runs; an
# untouched bundle is this campaign's own file and is replaced, and anything else — a hook
# somebody merged a check into, or wrote — is never overwritten, only reported.
SUPERSEDED = frozenset({'c02a58c70dddeba812740dd2f83a5be43c14ad8e6cd2e35cbba62355f42f8ecc',
                        'cd0a2f7f5b49b3557b1362a707347604f24cc136a3a96a3cb3fe7b956f52f7db',
                        '75fc8870c63073d3c9446110acc81b0d45c35dfd2d8c7d4357356d61e3c3906d'})


def install_hook():
    """Place the pre-push receipt check in this repository, refusing to displace another.

    The hook is the enforcement boundary: git hands it the pushed SHAs directly, so it
    holds regardless of how the push command was spelled. A foreign hook or a custom
    core.hooksPath is reported for the human to reconcile rather than overwritten.
    """
    source = Path(__file__).with_name('review_prepush.py')
    custom = subprocess.run(['git', 'config', '--get', 'core.hooksPath'], capture_output=True, text=True)
    if custom.returncode == 0:
        # A custom hooks directory is the user's: never write into it. Its pre-push
        # qualifies by behaviour alone, so a generated stub that delegates to a tracked
        # hook (husky's layout) qualifies when the hook it runs invokes the check.
        toplevel = Path(git('rev-parse', '--show-toplevel'))
        reconciled = (toplevel / Path(custom.stdout.strip()).expanduser()) / 'pre-push'
        require(reconciled.exists(),
                'core.hooksPath is set to ' + custom.stdout.strip() + ' and holds no pre-push; add one '
                'there (or in the tracked hook a generated stub delegates to) that invokes '
                + str(source) + ', and start again.')
        usable_hook(reconciled)
        return
    target = Path(git('rev-parse', '--git-common-dir')).resolve() / 'hooks' / 'pre-push'
    if target.exists() or target.is_symlink():
        require(not target.is_dir(),
                str(target) + ' is a directory, so git cannot run it as the pre-push hook. '
                + hook_remedy(target, source))
        text = target.read_text(errors='replace') if target.exists() else ''
        require(HOOK_MARKER in text,
                'A pre-push hook not managed by this campaign exists at ' + str(target)
                + '; merge the receipt check into it by hand, keeping its marker line, before starting.')
        # An untouched bundle from an earlier release carries an earlier receipt rule. It is
        # this campaign's own file, so it is replaced rather than reported; a symlink points
        # at somebody's arrangement and is never written through.
        if not target.is_symlink() and hashlib.sha256(target.read_bytes()).hexdigest() in SUPERSEDED:
            target.write_bytes(source.read_bytes())
            target.chmod(0o755)
            usable_hook(target)
            return
        # Carries the check at the current policy but is not the bundled file: merged or
        # edited by hand, so it is kept; the probe pushes decide whether it still enforces.
        usable_hook(target)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    target.chmod(0o755)


HOOK_SECONDS = 60
# How far inside (or outside) the waiver window a probe receipt is dated. It must exceed the
# time the hook reading it may take, or a hook that is merely slow is reported as a hook that
# disagrees: at a margin equal to HOOK_SECONDS, one that used its whole budget would watch a
# fresh waiver expire mid-run and refuse it, and the runtime would answer "shorter waiver
# window" for what was a timeout. Tied to the bound rather than repeated as a literal, so
# raising one raises the other.
PROBE_MARGIN = HOOK_SECONDS + 60


def run_hook(path, remote, line):
    """Run a pre-push hook as git does on the given push records; return its exit status."""
    # git runs a hook from the worktree root, and one without a shebang through sh.
    interpreter = [] if path.read_bytes().startswith(b'#!') else ['sh']
    refs = line.count('\n')
    try:
        probe = subprocess.run([*interpreter, str(path), *remote], input=line, capture_output=True,
                               text=True, timeout=HOOK_SECONDS, cwd=git('rev-parse', '--show-toplevel'))
    except subprocess.TimeoutExpired:
        raise ValueError(f'{path} did not finish within {HOOK_SECONDS} s when probed with a push of '
                         f'{refs} ref(s). ' + hook_remedy(path, Path(__file__).with_name('review_prepush.py')))
    except OSError as error:
        raise ValueError(f'{path} could not be run ({error.strerror}); fix its interpreter line. '
                         + hook_remedy(path, Path(__file__).with_name('review_prepush.py')))
    return probe.returncode


# Must exceed every BOUNDED EXECUTION one probe can make at its ceiling, not every push:
# the pushes were the only kind until a second appeared inside the window and the guard,
# counting pushes, went on passing a bound that no longer held.
# test_sweep_bound_outlasts_every_bounded_execution_of_one_probe counts both kinds.
PROBE_BOUND = 15 * HOOK_SECONDS


def sweep_probes(root):
    """Remove what an interrupted probe left behind, once older than a probe can be.

    Linked worktrees share the common directory, so a younger directory or ref may
    belong to a sibling's probe still in flight and is left alone.
    """
    for stale in root.glob('probe-*'):
        try:
            aged = time.time() - stale.stat().st_mtime > PROBE_BOUND
        except FileNotFoundError:  # a sibling's probe finished between the listing and the stat
            continue
        if aged:
            shutil.rmtree(stale, ignore_errors=True)
    refs = git('for-each-ref', '--format=%(refname) %(creatordate:unix)', 'refs/bymax-review/')
    for entry in refs.splitlines():
        name, created = entry.split()
        if time.time() - int(created) > PROBE_BOUND:
            subprocess.run(['git', 'update-ref', '-d', name], capture_output=True)


# What the view subprocess prefixes its answer with, so an empty answer is distinguishable
# from a hook that printed nothing at all.
VIEW_MARKER = 'bymax-hook-view:'


def hook_view(checker):
    """Resolve Codex the way the hook under test will, for the one question usable_hook asks
    of it: does this hook agree with the runtime about the machine?

    Nothing here decides what a probe receipt contains — waived_shape does, and says so.
    A hook that
    cannot be loaded as a module — a shell stub delegating to the checker, a copy from
    before waivers existed — has no view to borrow, and this runtime's own is used, which
    is agreement by default. A hook that exits, hangs, reads stdin or writes rubbish at
    import is the same case and must reach the same answer rather than the caller's process.
    """
    # In a subprocess, like every other hook execution here, and for the same reasons: a
    # hook somebody merged a check into runs that check at import, and in this process its
    # sys.exit() is a SystemExit no `except` for Exception catches and no caller expects,
    # while a read of stdin never returns. Bounded, fed nothing, and answered through a
    # marker so an exit that prints nothing is a fallback rather than a machine with no Codex.
    # The marker carries a nonce, so a hook that prints the fixed one at import announces a
    # view instead of being asked for one. It is not a defence against a hook that means to
    # lie: the driver is -c source the hook's own process can read. Nothing here can be —
    # the hook is the enforcement point, and a hostile one needs no view to defeat.
    marker = VIEW_MARKER + os.urandom(8).hex() + ':'
    driver = ('import importlib.machinery as loaders, importlib.util as util, sys\n'
              'loader = loaders.SourceFileLoader("bymax_hook_view", sys.argv[1])\n'
              'module = util.module_from_spec(util.spec_from_loader(loader.name, loader))\n'
              'loader.exec_module(module)\n'
              # A leading newline: a hook's unterminated write at import would otherwise
              # absorb this line and discard the answer with it.
              'print("\\n' + marker + '" + (module.resolve_codex() or ""))\n')
    try:
        probe = subprocess.run([sys.executable, '-c', driver, str(checker)],
                               capture_output=True, timeout=HOOK_SECONDS, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):  # unrunnable, or past the bound
        return resolve_codex()
    # Decoded leniently: stdout is a channel a hook may write anything to, and a strict
    # decode raises what is neither an OSError nor a SubprocessError, escaping the fallback
    # this function exists to provide.
    for line in reversed(probe.stdout.decode('utf-8', 'replace').splitlines()):
        if line.startswith(marker):
            return line[len(marker):] or None
    return resolve_codex()  # not importable, or not a checker that knows about waivers


def waived_shape(stale=False):
    """The receipt shape for a candidate whose Codex the runtime could not run.

    This is where that shape is defined; everything else points here rather than restating
    it, because a description kept in several places is one that goes stale in all but one.
    Built from this runtime's view, which usable_hook has already required the hook to
    share: where Codex is installed that is a quota waiver naming the resolved binary, and
    where it is not, an absent one. Nothing here runs the hook — every bounded execution
    inside a probe's window counts against the bound that lets a sibling sweep it.

    Both datings sit PROBE_MARGIN either side of the window's far edge, which is what pins a
    kept hook's window to this runtime's rather than merely bounding it from above. A hook
    with a shorter window refuses the current receipt; one with a longer window accepts the
    stale receipt; either way it disagrees about what a cleared receipt means, and the
    probes see it rather than the user's next push.
    """
    binary = resolve_codex()
    at = int(time.time()) - WAIVER_TTL + (-PROBE_MARGIN if stale else PROBE_MARGIN)
    waiver = dict(reason='quota' if binary else 'absent', at=at, binary=binary or '')
    return {'claude': {}, 'claude-b': {}}, waiver


def claude_waived_shape(sha, stale=False):
    """The receipt shape for a candidate whose Claude the runtime measured out of quota.

    Dated like waived_shape, so a hook with a shorter window refuses the current receipt and
    one with a longer window accepts the stale one. Nothing here runs the hook.
    """
    at = int(time.time()) - WAIVER_TTL + (-PROBE_MARGIN if stale else PROBE_MARGIN)
    waiver = dict(reason='quota', at=at, binary=resolve_claude() or '', head=sha, round=1)
    return {'codex': {}, 'codex-b': {}}, waiver


@contextlib.contextmanager
def probe_receipt(sha, held=True, legacy=False, waived=None, stale=False, claude_waived=False):
    """Hold a completed receipt for one commit only while this process probes the hook.

    Each probe gets a directory of its own, so concurrent starts in linked worktrees do
    not disturb each other. The receipt is valid only while its holder file is locked:
    the kernel drops the lock with the process, so a receipt orphaned by a kill names a
    commit nobody can push, whatever pid the system hands out next. With held=False the
    holder exists but is not locked; with legacy=True the receipt names a pid and nothing
    to hold. A checker must treat both as void: a probe receipt is valid only while held.
    With waived=True the receipt carries what waived_shape() builds, which a current hook
    must honour; with stale=True that waiver is past the window, which every hook must
    refuse. With claude_waived=True the receipt carries what claude_waived_shape(sha) builds,
    under the same dating rule.
    """
    root = Path(git('rev-parse', '--git-common-dir')).resolve() / 'bymax-review'
    root.mkdir(parents=True, exist_ok=True)
    sweep_probes(root)
    directory = Path(tempfile.mkdtemp(prefix='probe-', dir=root))
    receipt = dict(head=sha, cleared=True, policy=POLICY, reviews=dict(claude={}, codex={}),
                   probe_pid=os.getpid())
    if waived:
        receipt['reviews'], receipt['codex_waiver'] = waived_shape(stale)
    if claude_waived:
        receipt['reviews'], receipt['claude_waiver'] = claude_waived_shape(sha, stale)
    if not legacy:
        receipt['probe_lock'] = 'holder'
    (directory / 'completed-probe.json').write_text(json.dumps(receipt))
    with (directory / 'holder').open('w') as holder:
        if held:
            fcntl.flock(holder, fcntl.LOCK_EX)
        try:
            yield
        finally:
            shutil.rmtree(directory, ignore_errors=True)


def probe_commit(head, nonce):
    """Build the dangling child of HEAD the hook probe pushes; return its SHA.

    The message carries a nonce: two worktrees at the same HEAD probing within the same
    second would otherwise build the same commit, and one's temporary receipt would
    name the other's unreceipted push. The user's identity is used when git has one, so
    an author check in the hook sees a normal commit; a probe identity is the fallback.
    """
    command = ['commit-tree', head + '^{tree}', '-p', head, '-m', 'chore: bymax receipt probe ' + nonce]
    # Dated now whatever GIT_*_DATE the environment exports: the sweep reads this date.
    now = str(int(time.time()))
    env = dict(os.environ, GIT_AUTHOR_DATE=now, GIT_COMMITTER_DATE=now)
    own = subprocess.run(['git', *command], capture_output=True, text=True, env=env)
    if own.returncode == 0:
        return own.stdout.strip()
    return subprocess.run(['git', '-c', 'user.name=bymax-probe', '-c', 'user.email=probe@bymax.invalid', *command],
                          capture_output=True, text=True, check=True, env=env).stdout.strip()


def managed_hook(path):
    """Whether `start` would write the bundled checker here if this hook were missing.

    It writes only into the repository's own hooks directory, and only where core.hooksPath is
    unset: a custom hooks directory belongs to whoever configured it and is never written into.
    """
    custom = subprocess.run(['git', 'config', '--get', 'core.hooksPath'], capture_output=True, text=True)
    if custom.returncode == 0:
        return False
    try:
        return Path(path) == Path(git('rev-parse', '--git-common-dir')).resolve() / 'hooks' / 'pre-push'
    except subprocess.SubprocessError:
        return False


def hook_remedy(path, checker):
    """How to fix a hook that does not enforce, in the words that are true for THIS path.

    Refusals used to tell the reader to delete the hook and let start reinstall it. Where
    core.hooksPath is set that is not a remedy: start never writes there, so deleting leaves
    the repository with no check at all, and the next start can only say the directory holds no
    pre-push. The sentence was true for the default path and wrong for the other, and nothing
    asked which one it was about — so the question is asked once, here.

    What this answers is one question: given THIS path, is deleting the hook a remedy or a way
    to end up with no check at all. Which refusals ask it is not stated here, and that is
    deliberate. Every attempt to summarise that boundary in a sentence has been found false by
    a reviewer — the last claimed the helper answers a hook that is present and runnable, while
    a directory sitting at the hook path, a hook that outran its probe and one whose interpreter
    line could not be run all ask it — while a hook that is merely missing the executable bit is
    one of the refusals that does not, which is how close together these live. The enumeration is not a rule; it is a list the code decides case by
    case, and a list belongs in a test. test_the_refusals_that_want_a_different_remedy_are_named
    holds it, and a refusal that stops asking for this answer fails there.
    """
    if managed_hook(path):
        return (f'Delete it so start reinstalls the bundled hook, or point it at {checker}, '
                'keeping any check you merged in.')
    return (f'Point it at {checker}, keeping any check you merged in. Do not delete it: '
            'core.hooksPath names this directory, start never writes into one, and deleting it '
            'would leave this repository with no check at all.')


def usable_hook(path):
    """Refuse a marked hook git would skip, one for another policy, or one that ignores receipts.

    git runs only executable hooks, silently ignoring the rest. A bundled copy left by
    another policy declares that POLICY; kept as is, it would refuse every push once
    a campaign clears under the current policy, so it is refused here instead.
    """
    checker = Path(__file__).with_name('review_prepush.py')
    text = path.read_text(errors='replace')
    declared = re.search(r'^POLICY = (\d+)$', text, re.MULTILINE)
    require(declared is None or int(declared.group(1)) == POLICY,
            f'{path} carries the receipt check for policy {declared.group(1) if declared else "?"}, the '
            f'runtime is policy {POLICY}. ' + hook_remedy(path, checker))
    require(os.access(path, os.X_OK),
            f'{path} is not executable, so git would skip it: chmod +x it before starting.')
    # The marker is a claim; the pushes below are the check. The push is shaped like a real
    # one — a temporary ref, resolving to a dangling child of HEAD built from the current
    # tree in the user's own identity, fast-forwarding the current branch on origin's URL
    # — so a hook that also checks the ref, its tip, the parent, the author or the remote
    # passes those checks. The invariants a kept hook must uphold: a commit with no
    # receipt is refused; a commit named by a held probe receipt passes; a probe receipt
    # nobody holds (unlocked holder, or a pid with nothing to hold) is void; every record
    # of a multi-ref push is checked. A hook that exits 0 fails the first push; one that
    # refuses for a reason the probe does not satisfy fails the second, closed; one that
    # honours an unheld receipt fails the push carrying it; one that leaves any record of
    # a three-ref push unchecked fails the multi-ref push whose unreceipted commit it
    # skips. What the pushes establish is narrower than the invariants: a hook that filters
    # records by a property all three of the probe's records share can still miss one, and
    # hook code written to recognise the probe is trusted code. The probe raises the floor;
    # it does not certify the hook.
    # Asked once, before the probes open anything, and required to agree: a receipt names the
    # Codex its waiver was measured against and this hook re-resolves that name, so a hook
    # that computes it differently refuses every waived push. The waived probe below also
    # catches a hook whose answer diverges when git runs it, since the receipt it is shown
    # carries the runtime's name. This check is the one that survives a divergence the probe
    # cannot reach — one that appears only at import — and it names the disagreement outright
    # instead of reporting it as a refused push.
    view = hook_view(path)
    require(view == resolve_codex(),
            f'{path} resolves Codex to {view or "none"} while this runtime resolves '
            f'{resolve_codex() or "none"}. A waiver names the binary it was measured against and '
            'this hook re-resolves that name before honouring it, so every waived push would be '
            f'refused for a disagreement no message explains. Make it resolve Codex as {checker} '
            'does — delegating to that file is the surest way. ' + hook_remedy(path, checker))
    upholds(path, checker, *push_probes(path))


def upholds(path, checker, unreceipted, held, orphaned, legacy, partial, waived, stale,
            claude_quota=0, claude_stale=1):
    """What each probe push must have returned, and what its exit status means if not."""
    require(unreceipted != 0,
            f'{path} accepted a push of a commit with no receipt (exit 0), so it does not enforce '
            f'receipts. ' + hook_remedy(path, checker))
    require(held == 0,
            f'{path} refused a push of a commit that holds a completed receipt (exit {held}), so it '
            f'is not consulting receipts. ' + hook_remedy(path, checker))
    require(orphaned != 0 and legacy != 0,
            f'{path} accepted a push named only by an orphaned probe receipt (exit 0): it reads receipts '
            'without checking their holder: a probe receipt nobody holds is void. '
            + hook_remedy(path, checker))
    require(waived == 0,
            f'{path} refused a push of a commit whose receipt carries an independent second Claude '
            'review in place of a Codex this machine cannot run (exit ' + str(waived) + '). Either '
            'it predates that receipt shape, or it honours a shorter waiver window than this '
            'runtime; either way it would block every waived push in silence. '
            + hook_remedy(path, checker))
    require(stale != 0,
            f'{path} accepted a push named by a receipt whose Codex waiver is past the window (exit '
            '0), or honours a longer window than this runtime. A waiver is evidence about a machine '
            'at a moment, and the two sides must agree when it stops being evidence, or a receipt '
            f'means one thing here and another at the hook. ' + hook_remedy(path, checker))
    require(claude_quota == 0,
            f'{path} refused a push of a commit whose receipt carries two independent Codex reviews '
            f'in place of a Claude this machine measured out of quota (exit {claude_quota}). Either '
            'it predates that receipt shape, or it honours a shorter window than this runtime; '
            'either way it would block every such push in silence. ' + hook_remedy(path, checker))
    require(claude_stale != 0,
            f'{path} accepted a push named by a receipt whose Claude quota evidence is past the '
            'window (exit 0), or honours a longer window than this runtime. ' + hook_remedy(path, checker))
    require(all(status != 0 for status in partial),
            f'{path} accepted a push of three refs one of whose commits holds no receipt (exit 0). git '
            'hands a hook one record per pushed ref and every record must be checked; a hook that leaves '
            'one of them unchecked, whether by reading a fixed few or by filtering, misses the '
            f'unreceipted commit here. Make it check every record, as {checker} does. '
            + hook_remedy(path, checker))


def push_records(branch, head, refs, dangling, other):
    """git's stdin for the probe pushes: the single-ref one, and the three-ref ones.

    A record per ref, the first fast-forwarding the current branch and the rest creating
    their own remote ref (all-zero remote sha). git hands a hook one record per pushed ref,
    so the unreceipted commit takes each of the three positions in turn: a hook that leaves
    one record unchecked reads only receipted commits in the push whose unreceipted one it
    skips, exits 0, and is refused for it.
    """
    def push(*pairs):
        first = f'{pairs[0][0]} {pairs[0][1]} {branch} {head}\n'
        return first + ''.join(f'{name} {sha} {name} {"0" * 40}\n' for name, sha in pairs[1:])

    return push((refs[0], dangling)), (
        push((refs[0], dangling), (refs[1], other), (refs[2], dangling)),
        push((refs[1], other), (refs[0], dangling), (refs[2], dangling)),
        push((refs[0], dangling), (refs[2], dangling), (refs[1], other)))


def push_probes(path):
    """Run the hook on the probe push without a receipt, with a held one, with an unheld one,
    with a pid-only one, on three-ref pushes that give the unreceipted commit each position
    in turn, and with a receipt whose Codex review was waived — once current, once expired.

    Returns the exit statuses, with the multi-ref ones as a tuple. The refs exist only for
    the duration.
    """
    head = git('rev-parse', 'HEAD')
    nonce, second = os.urandom(8).hex(), os.urandom(8).hex()
    dangling, other = probe_commit(head, nonce), probe_commit(head, second)
    branch = git('symbolic-ref', '--quiet', 'HEAD')
    refs = ['refs/bymax-review/probe-' + nonce, 'refs/bymax-review/probe-' + second,
            'refs/bymax-review/probe-' + nonce + '-again']
    for name, sha in zip(refs, (dangling, other, dangling)):
        git('update-ref', name, sha)

    line, multi = push_records(branch, head, refs, dangling, other)
    url = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True)
    remote = ('origin', url.stdout.strip() if url.returncode == 0 else 'origin')
    try:
        unreceipted = run_hook(path, remote, line)
        if unreceipted == 0:
            return unreceipted, None, None, None, (), None, None, 0, 1
        with probe_receipt(dangling):
            held = run_hook(path, remote, line)
            partial = tuple(run_hook(path, remote, records) for records in multi)
        with probe_receipt(dangling, held=False):
            orphaned = run_hook(path, remote, line)
        with probe_receipt(dangling, legacy=True):
            legacy = run_hook(path, remote, line)
        with probe_receipt(dangling, waived=True):
            waived = run_hook(path, remote, line)
        with probe_receipt(dangling, waived=True, stale=True):
            stale = run_hook(path, remote, line)
        claude_quota, claude_stale = 0, 1  # no Claude to name: the shape cannot be probed
        if resolve_claude():
            with probe_receipt(dangling, claude_waived=True):
                claude_quota = run_hook(path, remote, line)
            with probe_receipt(dangling, claude_waived=True, stale=True):
                claude_stale = run_hook(path, remote, line)
    finally:
        for name in refs:
            git('update-ref', '-d', name)
    return unreceipted, held, orphaned, legacy, partial, waived, stale, claude_quota, claude_stale
