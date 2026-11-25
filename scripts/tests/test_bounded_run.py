"""A command a test runs through `run_bounded` leaves no process behind, however it ends."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from bounded_run import run_bounded


class BoundedRunTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ['rm', '-rf', str(self.folder)])
        self.child = self.folder / 'child'

    def child_pid(self):
        """The pid of the background job the command recorded, stopped at the end of the case if it still runs."""
        pid = int(self.child.read_text())
        self.addCleanup(self.stop, pid)
        return pid

    @staticmethod
    def stop(pid):
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass

    @staticmethod
    def alive(pid):
        """Whether the process still runs, allowing the moment init takes to reap what was killed."""
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            time.sleep(0.05)
        return True

    def test_a_command_that_never_ends_leaves_no_process_behind(self):
        """The loop and the job it started are both gone once the timeout has been raised."""
        command = f'sleep 300 & echo $! > {self.child}; while :; do sleep 1; done'
        with self.assertRaises(subprocess.TimeoutExpired):
            run_bounded(['bash', '-c', command], timeout=2)
        self.assertFalse(self.alive(self.child_pid()))

    def test_a_background_job_of_a_command_that_returned_is_stopped_too(self):
        """A command that exits normally cannot leave a job running behind it."""
        done = run_bounded(['bash', '-c', f'sleep 300 > /dev/null 2>&1 & echo $! > {self.child}; echo ok'], timeout=10)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, 'ok'))
        self.assertFalse(self.alive(self.child_pid()))

    def test_the_result_is_what_subprocess_run_would_have_returned(self):
        """Output, error output and the exit status come back as text."""
        done = run_bounded(['bash', '-c', 'echo out; echo err >&2; exit 3'], timeout=10)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (3, 'out\n', 'err\n'))


if __name__ == '__main__':
    unittest.main()
