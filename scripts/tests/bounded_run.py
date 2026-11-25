"""Run a command a test must not be able to leave behind.

`subprocess.run(..., timeout=)` kills only the process it started. A command that starts
children of its own (`bash -c 'x | sh'`, a loop, a background job) leaves them running after
the timeout, and a loop that never ends keeps running for hours. This runs the command in its
own process group and kills the whole group when it times out, and again when it returns, so
nothing it started outlives the call.
"""
import os
import signal
import subprocess


def run_bounded(args, timeout, **options):
    """`subprocess.run` with captured text output, in its own process group, with the group killed on exit.

    A timeout raises `subprocess.TimeoutExpired`, as `subprocess.run` does, after the group is gone.
    """
    options.setdefault('text', True)
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                          **options) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        finally:
            # The leader is its group's id, so this reaches every descendant that stayed in the group.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
