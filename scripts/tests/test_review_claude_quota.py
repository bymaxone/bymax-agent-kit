"""Quota-only reciprocal Claude fallback, without live reviewer execution."""
import copy
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2] / 'plugins/bymax-quality/scripts'
sys.path.insert(0, str(SCRIPTS))
import review_claude


class Flow:
    CLAUDE_SUBSTITUTE = 'codex-b'
    def __init__(self):
        self.state = dict(head='head', round=1, review_base='base', checks=[], reviews={})
    def locked(self, directory):
        return nullcontext()
    def read_state(self, directory):
        return copy.deepcopy(self.state)
    def save(self, directory, state):
        self.state = copy.deepcopy(state)
    def current(self, state):
        self.require(state['head'] == 'head', 'Candidate moved')
    def require(self, condition, message):
        if not condition:
            raise ValueError(message)
    def substitute_allowed(self, state, reviewer):
        return None
    def prompt(self, state, directory):
        return 'Review the candidate'
    def git_raw(self, *args):
        return 'diff'
    def for_a_reader(self, text):
        return text
    def claude_waiver_ok(self, waiver):
        return waiver.get('reason') == 'quota' and waiver.get('binary') == '/fixture/claude'
    def waiver_ok(self, waiver):
        return False
    def record(self, args, directory, state):
        state['reviews'][args.reviewer] = {'completed':True}
        self.save(directory,state)


class ClaudeQuotaTests(unittest.TestCase):
    def test_structured_budget_error_with_zero_exit_is_quota(self):
        """A CLI error envelope may exit zero while subscription usage is exhausted."""
        envelope = {'is_error':True,'result':"You've hit your limit · resets tomorrow"}
        self.assertEqual(review_claude.claude_verdict(envelope, '')[0], 'quota')

    def test_reports_quotes_auth_transient_and_command_budgets_never_waive(self):
        """Untrusted review prose and ordinary operational errors never substitute a reviewer."""
        samples = [
            ({'is_error':False,'result':'quota exceeded','structured_output':{'text':'usage limit'}}, ''),
            ({'is_error':True,'result':'The prompt says quota exceeded'}, ''),
            ({'is_error':True,'subtype':'error_max_budget_usd','result':'quota exceeded'}, ''),
            ({'is_error':True,'result':'Error: 429 rate limit exceeded'}, ''),
            ({'is_error':True,'result':'Error: authentication failed'}, ''),
            (None, 'Task evidence: quota exceeded\nPrompt discusses usage limit'),
            (None, 'Error: Network unavailable'),
            (None, 'Error: The report quotes quota exceeded'),
            (None, 'API Error: 429 {"error":{"type":"rate_limit_error","message":"Usage limit exceeded"}}'),
            (None, 'API Error: 401 {"error":{"type":"authentication_error","message":"quota exceeded"}}'),
        ]
        for envelope, stderr in samples:
            with self.subTest(envelope=envelope,stderr=stderr):
                self.assertNotEqual(review_claude.claude_verdict(envelope,stderr)[0], 'quota')

    def test_cli_limit_message_formats_are_quota_but_prose_is_not(self):
        for message in ('Claude AI usage limit reached|1760000000', '5-hour limit reached \u2219 resets 3pm',
                        'Weekly limit reached', 'Claude usage limit reached. Your limit will reset at 3pm'):
            self.assertEqual(review_claude.claude_verdict({'is_error': True, 'result': message}, '')[0], 'quota', message)
        for message in ('please reduce your limit of tokens', 'Usage limit notes in prompt'):
            self.assertEqual(review_claude.claude_verdict({'is_error': True, 'result': message}, '')[0], 'failed', message)

    def test_terminal_cli_error_line_is_quota(self):
        """Anchored fatal CLI diagnostics count; prompt text before them does not."""
        self.assertEqual(review_claude.claude_verdict(None, 'Prompt: usage limit\nError: Credit balance is too low')[0], 'quota')

    def test_runtime_quota_records_scope_without_report_and_reuses_waiver(self):
        """Only a measured primary quota error writes a candidate-and-round-bound waiver."""
        flow = Flow()
        def execute(command, **kwargs):
            kwargs['stdout'].write(json.dumps({'is_error':True,'result':"You've hit your limit"}))
            return subprocess.CompletedProcess(command,0)
        with tempfile.TemporaryDirectory() as box, \
                mock.patch.object(review_claude.review_prepush,'resolve_claude',return_value='/fixture/claude',create=True), \
                mock.patch.object(review_claude.subprocess,'run',side_effect=execute) as runner:
            state=review_claude.execute(Path(box),99,flow,'claude')
            waiver=state['claude_waiver']
            self.assertEqual((waiver['reason'],waiver['head'],waiver['round']),('quota','head',1))
            self.assertEqual(state['reviews'],{})
            self.assertEqual(state['claude_attempts'],1)
            self.assertTrue(Path(waiver['log']).is_file())
            self.assertEqual(review_claude.execute(Path(box),99,flow,'claude'),state)
            runner.assert_called_once()

    def test_absence_and_spent_attempts_do_not_create_a_waiver(self):
        """An unavailable executable or exhausted command budget is never account-quota evidence."""
        for binary, spent in ((None, 0), ('/fixture/claude', 2)):
            flow=Flow()
            flow.state['claude_attempts']=spent
            with self.subTest(binary=binary,spent=spent), tempfile.TemporaryDirectory() as box, \
                    mock.patch.object(review_claude.review_prepush,'resolve_claude',return_value=binary), \
                    mock.patch.object(review_claude.subprocess,'run') as runner:
                with self.assertRaises(ValueError):
                    review_claude.execute(Path(box),99,flow,'claude')
                self.assertNotIn('claude_waiver',flow.state)
                self.assertEqual(flow.state['claude_attempts'],spent)
                runner.assert_not_called()

    def test_candidate_move_during_quota_run_is_not_waived(self):
        """Quota evidence from an obsolete frozen candidate cannot apply to another candidate."""
        flow=Flow()
        def execute(command, **kwargs):
            kwargs['stdout'].write(json.dumps({'is_error':True,'result':"You've hit your limit"}))
            flow.state['round']=2
            return subprocess.CompletedProcess(command,0)
        with tempfile.TemporaryDirectory() as box, \
                mock.patch.object(review_claude.review_prepush,'resolve_claude',return_value='/fixture/claude'), \
                mock.patch.object(review_claude.subprocess,'run',side_effect=execute):
            with self.assertRaises(ValueError):
                review_claude.execute(Path(box),99,flow,'claude')
            self.assertNotIn('claude_waiver',flow.state)

    def test_incomplete_response_fails_without_waiver(self):
        """A successful process with no complete structured review cannot advance the campaign."""
        flow=Flow()
        def execute(command, **kwargs):
            kwargs['stdout'].write(json.dumps({'is_error':False,'result':'quota exceeded'}))
            return subprocess.CompletedProcess(command,0)
        with tempfile.TemporaryDirectory() as box, \
                mock.patch.object(review_claude.review_prepush,'resolve_claude',return_value='/fixture/claude',create=True), \
                mock.patch.object(review_claude.subprocess,'run',side_effect=execute):
            with self.assertRaises(ValueError):
                review_claude.execute(Path(box),99,flow,'claude')
            self.assertNotIn('claude_waiver',flow.state)


class CompleteReportTests(unittest.TestCase):
    def test_a_complete_primary_report_wins_over_stderr_quota_text(self):
        """A real completed primary review is recorded; its content cannot create a waiver."""
        flow=Flow()
        def execute(command, **kwargs):
            kwargs['stdout'].write(json.dumps({'is_error':False,'structured_output':{'complete':True}}))
            kwargs['stderr'].write('Error: quota exceeded')
            return subprocess.CompletedProcess(command,0)
        with tempfile.TemporaryDirectory() as box, \
                mock.patch.object(review_claude.review_prepush,'resolve_claude',return_value='/fixture/claude'), \
                mock.patch.object(review_claude.subprocess,'run',side_effect=execute):
            state=review_claude.execute(Path(box),99,flow,'claude')
            self.assertIn('claude',state['reviews'])
            self.assertNotIn('claude_waiver',state)


if __name__ == '__main__':
    unittest.main()
