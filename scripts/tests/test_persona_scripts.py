"""Gate layer: the helper scripts /bymax-qa:personas runs behave as its references say.

The store collector is driven with a fake fetcher, so no test reaches the network. The
day generator is checked on the flow text it writes, and the day runner on the order it
calls a fake `maestro` in and on where it stops.
"""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'plugins/bymax-qa/scripts'


def module(name):
    """Import a hyphenated script file as a module."""
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), SCRIPTS / f'{name}.py')
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


stores = module('persona-store-reviews')
days = module('persona-days')


def feed(*ids):
    """A review-feed page holding one entry per id, with the reviewer fields Apple sends."""
    entries = [{'id': {'label': i}, 'author': {'name': {'label': 'Real Person'}, 'uri': {'label': 'https://x'}},
                'im:rating': {'label': '2'}, 'title': {'label': 't'}, 'content': {'label': 'c'},
                'im:version': {'label': '1.0'}, 'updated': {'label': '2026-01-01T00:00:00-07:00'}} for i in ids]
    return {'feed': {'entry': entries[0] if len(entries) == 1 else entries}}


class FakeStore:
    """Answers URLs from a table; a list value is consumed one answer per call."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, url, timeout):
        self.calls.append(url)
        for prefix, answer in self.table.items():
            if url.startswith(prefix):
                if isinstance(answer, list):
                    answer = answer.pop(0) if len(answer) > 1 else answer[0]
                status, payload = answer
                return status, json.dumps(payload).encode() if payload is not None else b''
        return 404, b''


class StoreCollectorTest(unittest.TestCase):
    def run_main(self, argv, table):
        fake, pauses = FakeStore(table), []
        out = Path(tempfile.mkdtemp())
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink):
            code = stores.main(argv + ['--out', str(out)], fetch=fake, sleep=pauses.append)
        return code, out, fake, pauses

    def test_reviews_drop_the_reviewer_and_stop_at_the_first_empty_page(self):
        lookup = (200, {'results': [{'trackName': 'Rival', 'userRatingCount': 9}]})
        table = {stores.LOOKUP: lookup,
                 'https://itunes.apple.com/br/rss/customerreviews/page=1/': (200, feed('r1', 'r2')),
                 'https://itunes.apple.com/br/rss/customerreviews/page=2/': (200, feed('r3')),
                 'https://itunes.apple.com/br/rss/customerreviews/page=3/': (200, {'feed': {}})}
        code, out, fake, pauses = self.run_main(
            ['reviews', '--countries', 'br', '--apps', '123', '--pages', '5', '--retries', '1'], table)
        self.assertEqual(code, 0)
        reviews = json.loads((out / 'reviews.json').read_text())
        self.assertEqual([r['reviewId'] for r in reviews], ['r1', 'r2', 'r3'])
        self.assertNotIn('Real Person', (out / 'reviews.json').read_text())
        self.assertFalse(any('page=4' in url for url in fake.calls), 'paging went past an empty page')
        self.assertEqual(pauses, [2.0], 'the empty page was not retried exactly once')

    def test_an_empty_page_that_fills_on_retry_is_kept_and_every_attempt_is_logged(self):
        table = {stores.LOOKUP: (200, {'results': [{'trackName': 'Rival'}]}),
                 'https://itunes.apple.com/us/rss/customerreviews/page=1/': [(429, None), (200, {'feed': {}}),
                                                                            (200, feed('r9'))]}
        _, out, _, pauses = self.run_main(
            ['reviews', '--countries', 'us', '--apps', '7', '--pages', '1', '--retries', '4'], table)
        self.assertEqual([r['reviewId'] for r in json.loads((out / 'reviews.json').read_text())], ['r9'])
        self.assertEqual(pauses, [2.0, 4.0])
        log = (out / 'collection-log.tsv').read_text().splitlines()
        self.assertEqual(len([line for line in log if 'customerreviews' in line]), 3)

    def test_a_second_run_merges_into_the_corpus_without_duplicates(self):
        table = {stores.LOOKUP: (200, {'results': [{'trackName': 'Rival'}]}),
                 'https://itunes.apple.com/br/rss/customerreviews/page=1/': (200, feed('r1', 'r2'))}
        _, out, _, _ = self.run_main(['reviews', '--countries', 'br', '--apps', '1', '--pages', '1'], table)
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink):
            stores.main(['reviews', '--countries', 'br', '--apps', '1', '--pages', '1', '--out', str(out)],
                        fetch=FakeStore(table), sleep=lambda seconds: None)
        self.assertEqual(len(json.loads((out / 'reviews.json').read_text())), 2)

    def test_discovery_ranks_by_appearances_then_best_rank(self):
        table = {stores.SEARCH + 'term=a': (200, {'results': [{'trackId': 1, 'trackName': 'One'},
                                                             {'trackId': 2, 'trackName': 'Two'}]}),
                 stores.SEARCH + 'term=b': (200, {'results': [{'trackId': 2, 'trackName': 'Two',
                                                              'userRatingCount': 50}]})}
        _, out, _, _ = self.run_main(['discover', '--countries', 'br', '--terms', 'a', 'b'], table)
        ranked = json.loads((out / 'discovery.json').read_text())
        self.assertEqual([(e['id'], e['appearances'], e['best_rank']) for e in ranked], [('2', 2, 1), ('1', 1, 1)])
        self.assertEqual(ranked[0]['rating_count'], 50)

    def test_values_that_enter_a_url_path_are_refused_unless_well_formed(self):
        for argv in (['--countries', 'br/../x', '--apps', '1'], ['--countries', 'br', '--apps', '1?x=y'],
                     ['--countries', 'br', '--apps', '../1']):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                stores.parse(['reviews', '--out', '/nonexistent'] + argv)

    def test_a_not_found_listing_is_not_retried(self):
        fake, pauses = FakeStore({}), []
        client = stores.Client(Path(tempfile.mkdtemp()) / 'log.tsv', fake, pauses.append, retries=4)
        self.assertIsNone(client.get('https://itunes.apple.com/lookup?id=1'))
        self.assertEqual((len(fake.calls), pauses), (1, []))


class DayGeneratorTest(unittest.TestCase):
    def config(self, **extra):
        folder = Path(tempfile.mkdtemp())
        value = {'appId': "app.x'dev", 'persona': 'p4', 'first_date': '2026-11-05', 'first_day': 2,
                 'offset': '-03:00', 'pin_flow': 'pin.yaml',
                 'actions': {'N': {'id': 'done-.*'}, 'X': {'id': 'miss-.*', 'then': 'reason.yaml'},
                             'Y': {'id': 'unrec-.*', 'own_index': True}},
                 'plan': ['NN', 'N-N', '@XY'], 'extras': {'3': ['review.yaml']}}
        value.update(extra)
        (folder / 'days.json').write_text(json.dumps(value))
        return folder

    def generate(self, folder):
        return days.write_days(days.load(folder / 'days.json'), folder / 'flows')

    def test_each_day_pins_its_own_date_and_files_sort_in_day_order(self):
        folder = self.config()
        written = self.generate(folder)
        self.assertEqual([p.name for p in written], ['p4-02.yaml', 'p4-03.yaml', 'p4-04.yaml'])
        third = written[2].read_text()
        self.assertIn("PERSONA_STAMP: '2026-11-07T00:30:00-03:00'", third)
        self.assertIn(f"file: '{(folder / 'pin.yaml').resolve()}'", third)
        self.assertIn("appId: 'app.x''dev'", third)

    def test_a_skipped_item_moves_later_taps_to_the_next_match(self):
        second = self.generate(self.config())[1].read_text()
        indexes = [line.strip() for line in second.splitlines() if line.strip().startswith('index:')]
        self.assertEqual(indexes, ['index: 0', 'index: 0', 'index: 1', 'index: 1'])

    def test_an_own_list_action_always_takes_its_first_match_and_follow_ups_run(self):
        folder = self.config(plan=['-XY'])
        flow = self.generate(folder)[0].read_text()
        self.assertIn(f"runFlow: '{(folder / 'reason.yaml').resolve()}'", flow)
        unrec = flow.split("id: 'unrec-.*'")[1]
        self.assertIn('index: 0', unrec.splitlines()[1])

    def test_taps_are_required_unless_the_action_says_optional(self):
        flow = self.generate(self.config(plan=['N']))[0].read_text()
        self.assertNotIn('optional', flow)
        folder = self.config(plan=['N'], actions={'N': {'id': 'done', 'optional': True}})
        self.assertEqual(self.generate(folder)[0].read_text().count('optional: true'), 2)

    def test_extras_land_on_their_day_only(self):
        written = self.generate(self.config())
        self.assertEqual([('review.yaml' in p.read_text()) for p in written], [False, True, False])

    def test_bad_configs_are_refused(self):
        for bad in ({'plan': ['NZ']}, {'persona': '../x'}, {'clock': '7h'}, {'offset': '-3'},
                    {'actions': {'nn': {'id': 'x'}}}, {'first_date': '05/11/2026'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.generate(self.config(**bad))


class DayRunnerTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.flows = self.folder / 'flows'
        self.flows.mkdir()
        for day in (2, 10, 3, 11):
            (self.flows / f'p1-{day:02d}.yaml').write_text(f'day {day}\n')
        self.calls = self.folder / 'calls.txt'
        self.fake = self.folder / 'maestro'
        self.fake.write_text('#!/bin/bash\n'
                             f'echo "$*" >> "{self.calls}"\n'
                             'flow="${@: -1}"\n'
                             'printf png > "$(basename "$flow" .yaml).png"\n'
                             'if [ -n "${FAIL_ON:-}" ] && [[ "$flow" == *"$FAIL_ON"* ]]; then echo "FAILED"; exit 1; fi\n')
        self.fake.chmod(0o755)

    def run_days(self, *args, **env):
        environment = dict(os.environ, MAESTRO=str(self.fake), HOME=str(self.folder), **env)
        return subprocess.run(['bash', str(SCRIPTS / 'persona-run-days.sh'), str(self.flows), *args],
                              capture_output=True, text=True, env=environment, timeout=60)

    def called(self):
        return [line.split()[-1].rsplit('/', 1)[-1] for line in self.calls.read_text().splitlines()]

    def test_days_run_one_call_each_in_day_order_and_their_shots_are_kept(self):
        result = self.run_days(PERSONA_DEVICE='emulator-5554')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.called(), ['p1-02.yaml', 'p1-03.yaml', 'p1-10.yaml', 'p1-11.yaml'])
        self.assertIn('--device emulator-5554 test', self.calls.read_text())
        self.assertEqual(sorted(p.name for p in (self.flows / 'shots').iterdir()),
                         ['p1-02.png', 'p1-03.png', 'p1-10.png', 'p1-11.png'])
        self.assertEqual(len((self.flows / 'run-log.tsv').read_text().splitlines()), 4)

    def test_the_run_stops_at_the_first_failed_day(self):
        result = self.run_days(FAIL_ON='p1-03')
        self.assertEqual(result.returncode, 1)
        self.assertIn('day 3 FAILED', result.stdout)
        self.assertEqual(self.called(), ['p1-02.yaml', 'p1-03.yaml'])

    def test_a_range_runs_only_its_days_and_a_failing_hook_stops_before_maestro(self):
        self.assertEqual(self.run_days('3', '10').returncode, 0)
        self.assertEqual(self.called(), ['p1-03.yaml', 'p1-10.yaml'])
        self.calls.unlink()
        result = self.run_days(PERSONA_BEFORE_DAY='[ "$PERSONA_DAY" != 2 ]')
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.calls.exists(), 'maestro ran after the before-day hook failed')

    def test_bad_arguments_are_refused(self):
        self.assertEqual(self.run_days('x').returncode, 2)
        missing = subprocess.run(['bash', str(SCRIPTS / 'persona-run-days.sh'), str(self.folder / 'none')],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(missing.returncode, 2)


if __name__ == '__main__':
    unittest.main()
