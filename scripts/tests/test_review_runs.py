"""The matrix runner's runs: how a pytest run, a collect and an enumeration are started,
bounded by a deadline, stopped with their process group, and read."""
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
# The bench is test_review_matrix's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_matrix as matrix
from test_review_matrix import CASE, GUARDED, Bench, rule


class RunTests(unittest.TestCase):

    def test_a_mutant_that_hangs_a_case_is_stopped_and_restored(self):
        """A mutant that disables a loop's stop condition leaves pytest waiting forever, and
        without a deadline the matrix never reaches the restore and the source stays mutated.
        A run that never ends is refused like a crash, since it may hang before any test body
        runs; its process group dies with it, and the file is restored whatever happens."""
        floor = matrix.FLOOR
        matrix.FLOOR = 3
        self.addCleanup(setattr, matrix, 'FLOOR', floor)
        guard = GUARDED + '\n\ndef done():\n    return True\n'
        test = ('import os, subprocess, sys\nsys.path.insert(0, ".")\nfrom thing import done\n\n\n'
                'def test_waits():\n    if not done():\n'
                '        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])\n'
                '        open("grandchild.pid", "w").write(str(child.pid))\n'
                '    while not done():\n        pass\n')
        bench = Bench(self, guard=guard, test=test)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'return True',
                                     'becomes': 'return False', 'case': 'waits'}]))
        self.assertIn('timed out', str(caught.exception))
        self.assertEqual((bench.where / 'thing.py').read_text(), guard)
        # The whole group, not pytest alone: a process the test started dies with it.
        grandchild = int((bench.where / 'grandchild.pid').read_text())
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(grandchild, 0)

    def test_an_import_hang_is_not_a_catch(self):
        """A mutant that hangs the module while it is imported stops the run before any test
        body: counting the timeout as a catch would credit a test that never ran."""
        floor = matrix.FLOOR
        matrix.FLOOR = 3
        self.addCleanup(setattr, matrix, 'FLOOR', floor)
        guard = GUARDED + '\n\nREADY = True\nwhile not READY:\n    pass\n'
        bench = Bench(self, guard=guard, test=CASE)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'READY = True',
                                     'becomes': 'READY = False', 'case': 'over_the_limit'}]))
        self.assertIn('timed out', str(caught.exception))
        self.assertEqual((bench.where / 'thing.py').read_text(), guard)

    def test_an_interrupted_run_takes_its_pytest_with_it(self):
        """In a session of its own pytest does not hear the terminal's Ctrl-C, so an
        interrupted matrix would leave it running. Whatever stops the wait stops the group too."""
        bench = Bench(self, test='import os, time\n\n\ndef test_sleeps():\n'
                                 '    open("pytest.pid", "w").write(str(os.getpid()))\n    time.sleep(600)\n')
        def interrupt(*_):
            raise KeyboardInterrupt
        previous = signal.signal(signal.SIGALRM, interrupt)
        self.addCleanup(signal.signal, signal.SIGALRM, previous)
        signal.alarm(3)
        with self.assertRaises(KeyboardInterrupt):
            matrix.run_case(str(bench.where), None, ['test_thing.py::test_sleeps'])
        signal.alarm(0)
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(int((bench.where / 'pytest.pid').read_text()), 0)

    def test_an_enumeration_that_never_ends_is_refused(self):
        """A rule's enumeration command is the author's, and one that waits for input or loops
        would hold the matrix, and the correction that needs it, for good. Bounded, refused by
        name, and the process it started dies with it."""
        clean = matrix.CLEAN
        matrix.CLEAN = 10
        self.addCleanup(setattr, matrix, 'CLEAN', clean)
        bench = Bench(self)

        def unbounded(*_):
            raise AssertionError('the enumeration was never stopped')
        previous = signal.signal(signal.SIGALRM, unbounded)
        self.addCleanup(signal.signal, signal.SIGALRM, previous)
        self.addCleanup(signal.alarm, 0)
        signal.alarm(30)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='sleep 600 & echo $! > enumerate.pid; wait'))
        signal.alarm(0)
        self.assertIn('enumeration command did not finish', str(caught.exception))
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(int((bench.where / 'enumerate.pid').read_text()), 0)

    def test_an_enumeration_that_prints_past_a_count_is_refused(self):
        """An enumeration is read through the bounded tail a run is, so one that prints without
        end holds KEEP bytes rather than all of it until the deadline. Output that fills the
        tail is not a count, and is refused by name rather than counted as the rows left in it."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='python3 -c "print(\'1\\\\n\' * %d)"' % matrix.KEEP))
        self.assertIn('which is not a count', str(caught.exception))
        # Bytes that are not UTF-8 are measured as bytes: decoded and re-encoded, each would count
        # three, and a short output would read as one that filled the tail.
        self.assertEqual(matrix.enumerated(str(bench.where), {
            'rule': 'bytes', 'enumeration': 'python3 -c "import sys; sys.stdout.buffer.write('
                                            'bytes([255]) * 30000 + bytes([10, 49, 10]))"'}), 1)
        # Ten seconds, not five: the same deadline bounds the collect bench.run makes first.
        clean = matrix.CLEAN
        matrix.CLEAN = 10
        self.addCleanup(setattr, matrix, 'CLEAN', clean)
        began = time.monotonic()
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='yes 1'))
        self.assertIn('enumeration command did not finish', str(caught.exception))
        self.assertLess(time.monotonic() - began, 60)

    def test_a_case_may_take_the_cache_fixture_and_leaves_no_cache_in_the_tree(self):
        """pytest's cache provider stays loaded, so a case taking its `cache` fixture runs here as it
        does under plain pytest, and what the provider writes lands in a directory of the run's own:
        the collect's too, which a conftest can write to while collecting."""
        test = CASE + '\n\ndef test_remembers(cache):\n    cache.set("bench/seen", 1)\n    assert not over(9)\n'
        bench = Bench(self, test=test)
        (bench.where / 'conftest.py').write_text('def pytest_collection_modifyitems(config, items):\n'
                                                 '    config.cache.set("bench/collected", len(items))\n')
        subprocess.run(['git', '-C', str(bench.where), 'add', 'conftest.py'], check=True)
        subprocess.run(['git', '-C', str(bench.where), '-c', 'user.email=a@b.invalid', '-c',
                        'user.name=A', 'commit', '-q', '-m', 'conftest'], check=True)
        bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'value > LIMIT', 'becomes': 'True',
                                 'case': 'remembers'}]))
        self.assertFalse((bench.where / '.pytest_cache').exists())

    def test_a_run_keeps_only_the_tail_of_its_output(self):
        """A run that prints without end must not grow the process that restores the mutated
        file: each stream keeps its last KEEP bytes, and the summary line is still read
        from a run that printed far more than that past pytest's capture."""
        kept = [b'']
        matrix.keep_tail(io.BytesIO(b'x' * (3 * matrix.KEEP) + b'last'), kept)
        self.assertEqual(len(kept[0]), matrix.KEEP)
        self.assertTrue(kept[0].endswith(b'last'))
        bench = Bench(self, test='def test_loud(capsys):\n    with capsys.disabled():\n'
                                 '        print("x" * %d)\n' % (3 * matrix.KEEP))
        code, tail = matrix.run_case(str(bench.where), None, ['test_thing.py'])
        self.assertEqual(code, 0)
        self.assertIn('1 passed', tail)

    def test_a_reader_keeps_what_it_read_before_the_end(self):
        """The end of a pipe may never come: a descendant can hold it open, and on Linux closing
        it does not wake a blocked read. What was read before must already be kept, since that
        is where pytest's summary line is."""
        class Stalled:
            def __init__(self):
                self.sent, self.gate = False, threading.Event()

            def read(self, _):
                if not self.sent:
                    self.sent = True
                    return b'1 passed in 0.01s'
                self.gate.wait()
                return b''
        stream, kept = Stalled(), [b'']
        reader = threading.Thread(target=matrix.keep_tail, args=(stream, kept), daemon=True)
        reader.start()
        waited = time.monotonic() + 5
        while not kept[0] and time.monotonic() < waited:
            time.sleep(0.01)
        self.assertTrue(reader.is_alive())
        self.assertEqual(kept[0], b'1 passed in 0.01s')
        stream.gate.set()
        reader.join(5)

    def test_a_descendant_holding_the_pipe_does_not_hold_the_run(self):
        """A process the test detaches from pytest's group can keep the run's pipes open after
        pytest ends. The run must still end, with what it read: closing a pipe must not wait on
        the reader blocked in it."""
        bench = Bench(self, test='import subprocess, sys\n\n\ndef test_detach(capsys):\n'
                                 '    with capsys.disabled():\n'
                                 '        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(40)"],\n'
                                 '                                 start_new_session=True)\n'
                                 '    open("detached.pid", "w").write(str(child.pid))\n')
        pid = bench.where / 'detached.pid'

        def reap():
            try:
                os.kill(int(pid.read_text()), signal.SIGKILL)
            except (OSError, ValueError):
                pass
        self.addCleanup(reap)
        began = time.monotonic()
        code, tail = matrix.run_case(str(bench.where), None, ['test_thing.py'])
        self.assertLess(time.monotonic() - began, 25)
        self.assertEqual(code, 0)
        self.assertIn('1 passed', tail)

    def test_a_collect_keeps_only_the_tail_of_what_it_prints(self):
        """A plugin that prints through collection must not grow the process that reads the
        collect: each stream keeps its last KEEP bytes, and the collect still names its tests."""
        bench = Bench(self)
        (bench.where / 'conftest.py').write_text(
            'def pytest_collection_modifyitems(config, items):\n'
            '    capture = config.pluginmanager.getplugin("capturemanager")\n'
            '    with capture.global_and_fixture_disabled():\n'
            '        print("x" * %d)\n        print("last")\n' % (3 * matrix.KEEP))
        box = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, box, True)
        done, _ = matrix.collect_run(str(bench.where), str(bench.where), ['test_thing.py'], None, 't0k', box)
        self.assertLessEqual(len(done.stdout), matrix.KEEP)
        self.assertIn('\nlast\n', done.stdout)
        self.assertEqual(matrix.ids(str(bench.where), ['test_thing.py']), ['test_thing.py::test_over_the_limit'])

    def test_a_collect_that_never_ends_is_refused(self):
        """A collect runs the repository's import-time code, and a loop there that only a
        collect reaches never returns. Bounded, refused by name, and its process group dies."""
        clean = matrix.CLEAN
        matrix.CLEAN = 10
        self.addCleanup(setattr, matrix, 'CLEAN', clean)
        bench = Bench(self, test='import os, subprocess, sys\nif "--collect-only" in sys.argv:\n'
                                 '    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])\n'
                                 '    open("grandchild.pid", "w").write(str(child.pid))\n'
                                 '    while True:\n        pass\n\n\ndef test_thing():\n    assert True\n')

        def unbounded(*_):
            raise AssertionError('the collect was never stopped')
        previous = signal.signal(signal.SIGALRM, unbounded)
        self.addCleanup(signal.signal, signal.SIGALRM, previous)
        self.addCleanup(signal.alarm, 0)
        signal.alarm(30)
        with self.assertRaises(SystemExit) as caught:
            matrix.ids(str(bench.where), ['test_thing.py'])
        signal.alarm(0)
        self.assertIn('did not finish collecting', str(caught.exception))
        time.sleep(0.5)
        # The whole group, not pytest alone: a process the collect started dies with it.
        with self.assertRaises(ProcessLookupError):
            os.kill(int((bench.where / 'grandchild.pid').read_text()), 0)

    def test_a_collect_that_times_out_answers_nothing(self):
        """The campaign asks whether a changed file is a test by collecting its directory, and
        reads a refusal as "not a test module" when the file alone collects. A timeout is not
        that answer: beside a neighbour that loops on import, the changed test must come back
        unanswered, None, so the gate refuses rather than opens."""
        sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
        import review_evidence
        clean = matrix.CLEAN
        matrix.CLEAN = 3
        self.addCleanup(setattr, matrix, 'CLEAN', clean)
        bench = Bench(self)
        (bench.where / 'tests').mkdir()
        (bench.where / 'tests' / 'test_a.py').write_text('def test_a():\n    assert True\n')
        (bench.where / 'tests' / 'test_hang.py').write_text(
            'import sys\nif "--collect-only" in sys.argv:\n    while True:\n        pass\n')
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A',
                                     'commit', '-q', '-m', 'a test beside a looping neighbour']):
            subprocess.run(['git', '-C', str(bench.where), *args], check=True)
        here = os.getcwd()
        os.chdir(bench.where)
        self.addCleanup(os.chdir, here)
        self.assertIsNone(review_evidence.collects_a_test('tests/test_a.py'))



if __name__ == '__main__':
    unittest.main()
