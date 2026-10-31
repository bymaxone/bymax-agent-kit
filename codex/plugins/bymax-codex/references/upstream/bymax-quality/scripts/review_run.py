"""Gate execution layer: run a declared gate so that everything it started ends with it."""
import contextlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import threading
import time

from review_git import require
from review_matrix import kill_group

# Seconds a gate asked to stop has to clean up before its whole group is killed.
STOP_GRACE = 5


def runnable(command, where=None):
    """Refuse a gate command whose program cannot be executed, before anything records it.

    A gate is an argument list, and its first word is the program. `check -- "pnpm test:cov"`
    hands over ONE word holding a space, and so does zsh for an unquoted `$var`, which it does
    not split into words; a script path that is wrong is the same case. Recorded, such a gate
    never reports an exit status, and that unfinished attempt refuses every later step of the
    candidate. The program is resolved as the child would be: through $PATH for a bare name, as
    a path for one holding a slash, and executable either way. A relative path is read from
    `where` when given — the worktree root, where a context's gates are meant to run, since
    `start` may be run from anywhere — and from the caller's directory, where `check` runs it.
    """
    program = command[0]
    relative = where is not None and '/' in program and not os.path.isabs(program)
    if shutil.which(os.path.join(where, program) if relative else program):
        return
    words = program.split()
    require(len(words) < 2,
            'The gate command arrived as one argument, ' + repr(program) + ', so it would run a '
            'program named exactly that, which does not exist; nothing was recorded. Pass each word '
            'as its own argument: review_flow.py check -- ' + ' '.join(shlex.quote(w) for w in words)
            + ' (in zsh an unquoted $var is not split into words: write ${=var}, or the words '
            'themselves). In a context, declare it as "checks": [' + json.dumps(words + command[1:])
            + '].')
    raise ValueError('The gate program ' + repr(program) + ' does not resolve to an executable file '
            'from ' + (where or os.getcwd()) + ': no such file on $PATH or at that path, or it is not '
            'executable. Nothing was recorded; fix the path or its mode and run the gate again.')


def run_gate(command, output, timeout):
    """The gate's exit status.

    The gate runs in a session of its own, without a controlling terminal, so that its whole
    process group can be stopped when it is done: when it exits, times out, is interrupted, or
    the check's own group is hung up or terminated. A SIGKILL to the check cannot be caught,
    and leaves the gate running.
    """
    with signals_raised((signal.SIGTERM, signal.SIGHUP)), \
            subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                             start_new_session=True) as child:
        try:
            return child.wait(timeout=timeout)
        finally:
            stop_group(child)


def stop_group(child):
    """Ask the gate's group to stop, and kill what is left of it after STOP_GRACE.

    SIGTERM first, so a gate that cleans up on it can; SIGKILL for whatever still runs, also
    when a second signal ends the grace early.
    """
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        child.wait()
        return
    gone = False
    try:
        deadline = time.monotonic() + STOP_GRACE
        while not gone and time.monotonic() < deadline:
            child.poll()
            try:
                os.killpg(child.pid, 0)
            except (ProcessLookupError, PermissionError):
                gone = True
            else:
                time.sleep(0.05)
    finally:
        if not gone:
            kill_group(child)
        child.wait()


@contextlib.contextmanager
def signals_raised(signums):
    """Turn these signals into an exit while the block runs, so its cleanup runs first.

    Signal handlers belong to the main thread; elsewhere the block runs as it is. A signal the
    caller ignores, as nohup ignores SIGHUP, stays ignored.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def raised(signum, _frame):
        raise SystemExit(128 + signum)

    before = {signum: signal.signal(signum, raised) for signum in signums
              if signal.getsignal(signum) is not signal.SIG_IGN}
    try:
        yield
    finally:
        for signum, handler in before.items():
            signal.signal(signum, handler)
