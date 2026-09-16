"""Regression layer: exercise delivery continuity and a constrained independent Claude reviewer."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

import test_review_flow as fixtures


class DeliveryTests(unittest.TestCase):
    """Drive public commands against isolated repositories without calling real models."""

    def setUp(self):
        """Reuse the repository fixture without rerunning its inherited test suite."""
        self.case = fixtures.ReviewFlowTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def enroll(self):
        """Enable delivery mode for this fixture's fixed context."""
        c = self.case
        return c.flow('start', '--autonomous', '--base', c.base, '--context', str(c.context))

    def test_six_candidates_across_completed_push_campaigns(self):
        """Successful intermediate receipts never renew the PR correction budget."""
        c = self.case
        self.enroll()
        for number in range(1, 7):
            state = c.flow('status')
            self.assertEqual(state['round'], number)
            self.assertEqual(state['delivery_used'], number)
            c.complete()
            c.push('git push origin HEAD')
            if number < 6:
                previous = state['head']
                c.commit('correction ' + str(number))
                state = c.start(correction=True, answers=['code.txt:bot-thread-' + str(number)])
                self.assertEqual(state['review_base'], previous)
        c.commit('beyond budget')
        c.start(correction=True, answers=['code.txt:bot-thread-7'], ok=False)
        c.push('git push origin HEAD', ok=False)

    def test_a_spent_budget_continues_only_by_a_recorded_decision(self):
        """The alarm stays an alarm: deleting the ledger is forbidden, extending it is recorded."""
        c = self.case
        self.enroll()
        for number in range(1, 6):
            c.complete()
            c.commit('correction ' + str(number))
            c.start(correction=True, answers=['code.txt:bot-thread-' + str(number)])
        c.complete()
        c.commit('seventh')
        refused = c.start(correction=True, answers=['code.txt:bot-thread-7'], ok=False).stderr
        self.assertIn('--extend-delivery', refused)
        state = c.start(correction=True, answers=['code.txt:bot-thread-7'],
                        extend='Max decided to continue after reading the six-candidate alarm')
        self.assertEqual(state['round'], 7)
        self.assertEqual(state['max_rounds'], 12)
        self.assertIn('extended by a recorded decision', c.text('prompt'))

    def test_a_correction_after_clearance_names_what_it_answers(self):
        """No open findings after a clearance, so the scope rule measures against the answers."""
        c = self.case
        self.enroll()
        c.complete()
        (c.repo / 'unasked.txt').write_text('a mechanism nobody asked for\n')
        c.git('add', '-A')
        c.git('commit', '-qm', 'a correction that says nothing about what it answers')
        silent = c.start(correction=True, ok=False).stderr
        self.assertIn('--answers', silent)
        # Declared answers are measured against the reviewed tree, so an unnamed file still widens.
        widened = c.start(correction=True, answers=['code.txt:bot-thread'], ok=False).stderr
        self.assertIn('unasked.txt', widened)
        # And an answer naming no file in the reviewed candidate is refused, not ignored.
        nowhere = c.start(correction=True, answers=['ghost.txt:bot-thread'], ok=False).stderr
        self.assertIn('name none: ghost.txt', nowhere)
        state = c.start(correction=True, answers=['code.txt:bot-thread'],
                        widen='fixture: the bot asked for a new file')
        self.assertEqual(state['answers'], ['code.txt:bot-thread'])
        self.assertIn('declared by the author as: code.txt:bot-thread', c.text('prompt'))

    def test_repeated_start_and_archive_do_not_renew_budget(self):
        """Same-head retries are free; moving campaign state aside preserves consumption."""
        c = self.case
        self.enroll()
        self.assertEqual(self.enroll()['delivery_used'], 1)
        c.report('claude')
        c.report('codex')
        c.triage()
        state = c.flow('status')
        directory = Path(state['directory'])
        directory.rename(directory.with_name(directory.name + '.archived'))
        c.commit('after authorized archive')
        state = c.flow('start', '--base', c.base, '--context', str(c.context),
                       '--after-archived', 'Fixture explicit authorization')
        self.assertEqual(state['delivery_used'], 2)
        self.assertEqual(state['max_rounds'], 6)

    def test_changed_scope_does_not_silently_start_new_delivery(self):
        """A cleared receipt is not permission to change the delivery contract."""
        c = self.case
        self.enroll()
        c.complete()
        c.commit('different request')
        context = json.loads(c.context.read_text())
        context['intent'] = 'Unrelated rewrite'
        c.context.write_text(json.dumps(context))
        c.start(correction=True, ok=False)

    def fake_claude(self, response):
        """Install a fixture executable that captures its actual argv and supplied scope."""
        c = self.case
        directory = c.root / 'bin'
        directory.mkdir()
        binary = directory / 'claude'
        capture = c.root / 'invocation.json'
        binary.write_text(f'#!{sys.executable}\nimport sys,json,pathlib\n'
                          f'pathlib.Path({str(capture)!r}).write_text(json.dumps(dict(argv=sys.argv, prompt=sys.stdin.read())))\n'
                          f'print({json.dumps(response)!r})\n')
        binary.chmod(0o755)
        env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ['PATH'])
        env.pop('CLAUDECODE', None)
        return env, capture

    def test_codex_host_can_record_real_cli_shaped_claude_output(self):
        """Only the structured matching report from a read-only CLI invocation is recorded."""
        c = self.case
        state = self.enroll()
        report = dict(status='completed', head=state['head'], base=state['review_base'],
                      summary='Inspected fixture', findings=[], resolutions=[])
        env, capture = self.fake_claude(dict(structured_output=report, is_error=False))
        run = subprocess.run([sys.executable, str(fixtures.FLOW), 'claude'], cwd=c.repo,
                             env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(c.flow('status')['reviews']['claude'], report)
        invocation = json.loads(capture.read_text())
        args = invocation['argv']
        self.assertEqual(args[args.index('--tools') + 1], 'Read,Grep,Glob')
        self.assertIn('--strict-mcp-config', args)
        self.assertIn('--disable-slash-commands', args)
        self.assertIn('+candidate', invocation['prompt'])
        self.assertIn(state['head'], invocation['prompt'])
        c.report('codex')
        c.triage()
        c.checks()
        self.assertTrue(c.flow('finish')['cleared'])

    def test_failed_claude_is_bounded_and_never_certifies(self):
        """A schema-shaped incomplete report spends an attempt but never authorizes push."""
        c = self.case
        self.enroll()
        env, _ = self.fake_claude(dict(structured_output={'status': 'incomplete'}))
        for _ in range(3):
            run = subprocess.run([sys.executable, str(fixtures.FLOW), 'claude'], cwd=c.repo,
                                 env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 2)
        state = c.flow('status')
        self.assertEqual(state['claude_attempts'], 2)
        self.assertNotIn('claude', state['reviews'])
        c.push('git push origin HEAD', ok=False)

    def test_claude_concurrency_and_stale_result(self):
        """A live reviewer excludes duplicates, permits other reports and cannot certify old HEAD."""
        c = self.case
        state = self.enroll()
        report = dict(status='completed', head=state['head'], base=state['review_base'],
                      summary='Fixture', findings=[], resolutions=[])
        env, _ = self.fake_claude(dict(structured_output=report))
        binary = c.root / 'bin/claude'
        ready, release = c.root / 'ready', c.root / 'release'
        source = binary.read_text().replace('import sys,json,pathlib', 'import sys,json,pathlib,time')
        source = source.replace('print(', f'pathlib.Path({str(ready)!r}).touch()\n'
                                f'while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\nprint(', 1)
        binary.write_text(source)
        process = subprocess.Popen([sys.executable, str(fixtures.FLOW), 'claude'], cwd=c.repo,
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            duplicate = subprocess.run([sys.executable, str(fixtures.FLOW), 'claude'], cwd=c.repo,
                                       env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn('already running', duplicate.stderr)
            self.assertEqual(c.flow('status')['claude_attempts'], 1)
            c.report('codex')
            c.commit('changed during review')
            release.touch()
            _, error = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 2, error)
            self.assertNotIn('claude', c.flow('status')['reviews'])
        finally:
            release.touch()
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

    def test_hook_routes_unreviewed_push_back_to_the_agent(self):
        """The hook requests automatic certification, leaving the original push unexecuted."""
        c = self.case
        payload = dict(cwd=str(c.repo), tool_input=dict(command='git push origin HEAD:feature'))
        run = subprocess.run([sys.executable, str(fixtures.PUSH)], input=json.dumps(payload),
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn('AUTOMATIC CONTINUATION', run.stderr)
        self.assertIn('start --autonomous', run.stderr)
        self.assertIn('original push destination/refspec', run.stderr)


if __name__ == '__main__':
    unittest.main()
