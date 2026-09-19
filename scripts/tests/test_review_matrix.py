"""The matrix runner: what it refuses, and what it records."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_matrix as matrix                                      # noqa: E402

GUARDED = 'LIMIT = 10\n\n\ndef over(value):\n    return value > LIMIT\n'
CASE = ('import sys\nsys.path.insert(0, ".")\nfrom thing import over\n\n\n'
        'def test_over_the_limit():\n    assert over(11)\n    assert not over(9)\n')


class Bench:
    """A tiny repository with one rule, one guard and one case that covers it."""

    def __init__(self, case, guard=GUARDED, test=CASE):
        self.where = Path(tempfile.mkdtemp())
        case.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.where)]))
        (self.where / 'thing.py').write_text(guard)
        (self.where / 'test_thing.py').write_text(test)
        subprocess.run(['git', 'init', '-q', str(self.where)], check=True)
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A',
                                     'commit', '-q', '-m', 'x']):
            subprocess.run(['git', '-C', str(self.where), *args], check=True)

    def spec(self, body):
        path = self.where / 'matrix.json'
        path.write_text(json.dumps(body))
        return str(path)

    def run(self, body, out=None):
        return matrix.record(str(self.where), self.spec(body), ['test_thing.py'], out=out)


def rule(**over):
    body = {'rule': 'one mutant per comparison the guard makes',
            'enumeration': 'grep -c ">" thing.py',
            'mutants': [{'file': 'thing.py', 'anchor': 'value > LIMIT',
                         'becomes': 'True', 'case': 'over_the_limit'}]}
    body.update(over)
    return [body]


class AnchorTests(unittest.TestCase):

    def test_an_anchor_that_matches_nothing_is_refused(self):
        """A mutation that never landed is a run that proves nothing, and its output reads
        as success. This package's memory records one that printed `69 passed` that way."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'absent', 'becomes': 'x',
                                     'case': 'over_the_limit'}]))
        self.assertIn('occurs 0 times', str(caught.exception))

    def test_an_anchor_that_matches_twice_is_refused(self):
        """The enumeration count is held at one so the ambiguous anchor is the only thing
        that can fail here; without that, the shorter-list refusal fires first and this case
        passes for a reason it does not name."""
        bench = Bench(self, guard='LIMIT = 10\nSPARE = LIMIT\n\n\ndef over(value):\n    return value > LIMIT\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='echo 1',
                           mutants=[{'file': 'thing.py', 'anchor': 'LIMIT', 'becomes': '1',
                                     'case': 'over_the_limit'}]))
        self.assertIn('occurs 3 times', str(caught.exception))


class MeaningTests(unittest.TestCase):

    def test_a_case_that_already_fails_is_refused(self):
        """Failing with a mutant says nothing when it fails without one."""
        bench = Bench(self, test=CASE.replace('assert over(11)', 'assert over(1)'))
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule())
        self.assertIn('does not pass on the clean tree', str(caught.exception))

    def test_a_surviving_mutant_is_the_finding(self):
        """A guard whose case cannot tell the mutant from the original is decoration."""
        bench = Bench(self, test='def test_over_the_limit():\n    assert True\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule())
        self.assertIn('survived', str(caught.exception))

    def test_a_mutant_that_only_breaks_the_import_is_refused(self):
        """A crash is not a measurement. A mutant that stops the module loading makes every
        case error, which reads as caught while the case never ran — measured on this file's
        own fixtures, where two mutants recorded 'caught 1 error'."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'def over(value):',
                                     'becomes': 'def over(', 'case': 'over_the_limit'}]))
        self.assertIn('stopped the tree from loading', str(caught.exception))

    def test_a_caught_mutant_passes_and_the_tree_is_restored(self):
        bench = Bench(self)
        payload = bench.run(rule())
        self.assertEqual(payload['survivors'], [])
        self.assertEqual(payload['mutants'], 1)
        self.assertEqual((bench.where / 'thing.py').read_text(), GUARDED)

    def test_the_tree_is_restored_even_when_the_run_refuses(self):
        """A runner that leaves a mutant behind poisons every measurement after it."""
        bench = Bench(self, test='def test_over_the_limit():\n    assert True\n')
        with self.assertRaises(SystemExit):
            bench.run(rule())
        self.assertEqual((bench.where / 'thing.py').read_text(), GUARDED)


class EnumerationTests(unittest.TestCase):

    def test_a_rule_that_declares_no_enumeration_is_refused(self):
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration=''))
        self.assertIn('declares no enumeration', str(caught.exception))

    def test_a_list_shorter_than_its_own_command_says_is_refused(self):
        """The check the whole thing exists for: a list shorter than the rule's own command
        enumerates is a case nothing covers, and it used to be the silent default."""
        bench = Bench(self, guard='LIMIT = 10\n\n\ndef over(v):\n    return v > LIMIT or v > 99\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='grep -o ">" thing.py | grep -c ">"',
                           mutants=[{'file': 'thing.py', 'anchor': 'v > LIMIT', 'becomes': 'True',
                                     'case': 'over_the_limit'}]))
        self.assertIn('short by 1', str(caught.exception))

    def test_not_derivable_by_command_is_allowed_only_with_a_reason(self):
        """Saying a rule cannot be enumerated mechanically is worth more than a fake command,
        so it is permitted — and it must say why, because that is the whole content."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='not derivable by command'))
        self.assertIn('does not say why', str(caught.exception))
        payload = bench.run(rule(enumeration='not derivable by command',
                                 why='the states are semantic, not syntactic'))
        self.assertEqual(payload['survivors'], [])

    def test_a_command_that_answers_nothing_is_not_an_enumeration(self):
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='true'))
        self.assertIn('produced no count', str(caught.exception))


class RecordTests(unittest.TestCase):

    def test_the_record_binds_to_the_head_and_the_mutated_files(self):
        """A record that does not name the tree it measured can be reused for another one."""
        bench = Bench(self)
        out = bench.where / 'rec.json'
        payload = bench.run(rule(), out=str(out))
        stored = json.loads(out.read_text())
        self.assertEqual(stored['head'], payload['head'])
        self.assertTrue(stored['head'])
        before = stored['tree']
        (bench.where / 'thing.py').write_text(GUARDED + '\nEXTRA = 1\n')
        self.assertNotEqual(bench.run(rule())['tree'], before)


if __name__ == '__main__':
    unittest.main()
