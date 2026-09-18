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
        c.checks()
        self.assertIn('by a recorded decision', c.text('prompt'))

    def test_a_cleared_campaign_moved_aside_continues_only_by_a_recorded_decision(self):
        """Nothing is rebuilt from the ledger; a full first round is what the decision buys."""
        c = self.case
        first = self.enroll()
        c.complete()
        directory = Path(c.flow('status')['directory'])
        directory.rename(directory.with_name(directory.name + '.archived'))
        (c.repo / 'unasked.txt').write_text('a file the bot asked for\n')
        c.git('add', '-A')
        c.git('commit', '-qm', 'the next candidate, with its campaign state moved aside')
        plain = c.flow('start', '--base', c.base, '--context', str(c.context), ok=False).stderr
        self.assertIn('--after-archived', plain)
        self.assertIn(first['head'][:12], plain)
        # --answers belongs to a correction round; there is none to continue.
        answered = c.start(correction=True, answers=['code.txt:bot-thread'], ok=False).stderr
        self.assertIn('--after-archived', answered)
        state = c.flow('start', '--base', c.base, '--context', str(c.context),
                       '--after-archived', 'fixture: Max decided to re-review in full')
        self.assertEqual((state['round'], state['review_base'], state['delivery_used']), (1, c.base, 2))
        self.assertEqual(state['reviews'], {})
        self.assertNotIn('unasked.txt', c.text('status'))  # nothing about scope is presumed
        live = Path(state['directory'])
        self.assertEqual(sorted(p.name for p in live.iterdir() if p.name.startswith('completed-')), [],
                         'a receipt was written for a head nobody reviewed in this campaign')
        c.checks()
        prompt = c.text('prompt')
        self.assertIn('Round 1/6', prompt)
        self.assertIn('Max decided to re-review in full', prompt)
        self.assertNotIn('had cleared', prompt)
        c.push('git push origin HEAD', ok=False)

    def test_an_uncleared_campaign_moved_aside_is_never_recovered_as_cleared(self):
        """Recovery presumes nothing: an open P1 in a moved-aside campaign stays in scope."""
        c = self.case
        (c.repo / 'bad.txt').write_text('unsafe thing\\n')
        c.git('add', '-A')
        c.git('commit', '-qm', 'add the file the finding is about')
        self.enroll()
        c.report('claude', [dict(id='bad.txt:unsafe-thing', kind='defect', priority='P1',
                                 evidence='unsafe')])
        c.report('codex')
        c.triage([dict(id='claude::bad.txt:unsafe-thing', status='open', evidence='Confirmed')])
        directory = Path(c.flow('status')['directory'])
        directory.rename(directory.with_name(directory.name + '.archived'))
        c.commit('touch only code.txt')
        probe = c.root / 'probe.json'
        probe.write_text(json.dumps([dict(command='c', expected='e', observed='e')]))
        sneaky = c.flow('start', '--base', c.base, '--context', str(c.context),
                        '--after-archived', 'x', '--probe', str(probe),
                        '--no-regression-reason', 'f', '--answers', 'code.txt:bot', ok=False)
        self.assertIn('--answers is for a correction after a cleared candidate', sneaky.stderr)
        self.assertIn('first round', sneaky.stderr)
        state = c.flow('start', '--base', c.base, '--context', str(c.context),
                       '--after-archived', 'x')
        self.assertEqual(state['round'], 1)
        self.assertEqual(state['review_base'], c.base)
        self.assertIn('bad.txt', c.git('diff', '--name-only', state['review_base'], state['head']))

    def test_a_cleared_head_whose_state_was_moved_aside_is_not_recertified(self):
        """A receipt is not rebuilt from the ledger: the same head is reviewed again, in full."""
        c = self.case
        self.enroll()
        c.complete()
        directory = Path(c.flow('status')['directory'])
        directory.rename(directory.with_name(directory.name + '.archived'))
        refused = c.flow('start', '--base', c.base, '--context', str(c.context), ok=False).stderr
        self.assertIn('--after-archived', refused)
        state = c.flow('start', '--base', c.base, '--context', str(c.context), '--after-archived', 'x')
        self.assertEqual((state['round'], state['cleared'], state['reviews']), (1, False, {}))
        self.assertFalse((Path(state['directory']) / ('completed-' + state['head'] + '.json')).exists())
        # The receipt itself survives in the moved-aside directory: that head was reviewed
        # and cleared, and a rename does not undo it. What cannot happen is a second one.
        c.push('git push origin HEAD')

    def test_a_changed_scope_with_an_extension_records_nothing(self):
        """The decision is written in the same ledger write as the head it authorises."""
        c = self.case
        self.enroll()
        for number in range(1, 6):
            c.complete()
            c.commit('correction ' + str(number))
            c.start(correction=True, answers=['code.txt:bot-thread-' + str(number)])
        c.complete()
        c.commit('seventh')
        context = json.loads(c.context.read_text())
        original = c.context.read_text()
        context['intent'] = 'a different request'
        c.context.write_text(json.dumps(context))
        refused = c.start(correction=True, answers=['code.txt:t7'], extend='Max decided', ok=False).stderr
        self.assertIn('scope changed', refused.lower())
        directory = Path(c.flow('status')['directory'])
        ledger = json.loads((directory.parent / 'deliveries' / (directory.name + '.json')).read_text())
        self.assertNotIn('extensions', ledger, 'a refused start wrote the decision')
        c.context.write_text(original)
        state = c.start(correction=True, answers=['code.txt:t7'], extend='Max decided')
        self.assertEqual((state['round'], state['max_rounds']), (7, 12))

    def test_answers_are_refused_while_findings_are_open(self):
        """A declared answer must not stand in for --widen-scope or --nit-round."""
        c = self.case
        self.enroll()
        c.report('claude', [dict(id='code.txt:nit', kind='nit', priority='P3', evidence='reads oddly')])
        c.report('codex')
        c.triage([dict(id='claude::code.txt:nit', status='open', evidence='Confirmed')])
        (c.repo / 'other.txt').write_text('something else\n')
        c.commit('fix')
        refused = c.start(correction=True, nit='', answers=['other.txt:bot-thread'], ok=False).stderr
        self.assertIn('--answers is for a correction after a cleared candidate', refused)
        state = c.start(correction=True, widen='fixture: the fix needs other.txt')
        self.assertEqual(state['answers'], [])

    def test_an_extension_needs_a_spent_budget_and_a_reason(self):
        """A flag passed early, blank, or on a refused start must not pre-buy a budget."""
        c = self.case
        self.enroll()
        early = c.start(extend='too soon', ok=False).stderr
        self.assertIn('not spent', early)
        for number in range(1, 6):
            c.complete()
            c.commit('correction ' + str(number))
            c.start(correction=True, answers=['code.txt:bot-thread-' + str(number)])
        c.complete()
        c.commit('seventh')
        blank = c.start(correction=True, answers=['code.txt:t'], extend='   ', ok=False).stderr
        self.assertIn('needs a reason', blank)
        c.start(correction=True, answers=['code.txt:t'], extend='first decision')
        self.assertEqual(c.flow('status')['max_rounds'], 12)
        for number in range(7, 12):
            c.complete()
            c.commit('correction ' + str(number))
            c.start(correction=True, answers=['code.txt:bot-thread-' + str(number)])
        c.complete()
        c.commit('thirteenth')
        c.start(correction=True, answers=['code.txt:t'], extend='second decision')
        c.checks()
        prompt = c.text('prompt')
        self.assertIn('extended 2 time(s)', prompt)
        self.assertIn('first decision', prompt)
        self.assertIn('second decision', prompt)

    def test_an_answer_carries_a_slug(self):
        """A bare path gives the reviewers no invariant to judge against."""
        c = self.case
        self.enroll()
        c.complete()
        c.commit('fix')
        bare = c.start(correction=True, answers=['code.txt'], ok=False).stderr
        self.assertIn('no slug: code.txt', bare)

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
        c.checks()
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
        # The moved-aside campaign never cleared, so it is an abandoned campaign: a full
        # first round against the original base, with its own recorded authorization.
        state = c.flow('start', '--base', c.base, '--context', str(c.context),
                       '--after-archived', 'Fixture explicit authorization')
        self.assertEqual(state['delivery_used'], 2)
        self.assertEqual(state['max_rounds'], 6)
        self.assertEqual(state['round'], 1)
        self.assertEqual(state['review_base'], c.base)
        c.checks()
        prompt = c.text('prompt')
        self.assertIn('kept aside without clearing', prompt)
        self.assertNotIn('had cleared', prompt)

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

    def test_the_claude_adapter_checks_the_gates_before_reserving_its_attempt(self):
        """The codex adapter's gate line is pinned by a case; this one's was not.

        Both reviewers said so and both were right: my probe for that correction mutated the
        two adapters together, so the one failing case could not tell which line it pinned, and
        deleting the claude adapter's line alone left the whole suite green. Nothing in either
        suite reached that module except through a path that had already run the gates.

        The attempt must survive the refusal, because spending it is the defect: two refusals
        would exhaust the per-candidate budget with nothing read.
        """
        c = self.case
        self.enroll()
        env, _ = self.fake_claude(dict(structured_output={}, is_error=False))
        run = subprocess.run([sys.executable, str(fixtures.FLOW), 'claude'], cwd=c.repo,
                             env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 2, run.stdout)
        self.assertIn('have not run on this candidate', run.stderr)
        self.assertEqual(c.flow('status').get('claude_attempts', 0), 0)
        self.assertNotIn('claude', c.flow('status')['reviews'])

    def test_codex_host_can_record_real_cli_shaped_claude_output(self):
        """Only the structured matching report from a read-only CLI invocation is recorded."""
        c = self.case
        state = self.enroll()
        report = dict(status='completed', head=state['head'], base=state['review_base'],
                      summary='Inspected fixture', findings=[], resolutions=[])
        env, capture = self.fake_claude(dict(structured_output=report, is_error=False))
        c.checks()
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
            c.checks()
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
        c.checks()
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
