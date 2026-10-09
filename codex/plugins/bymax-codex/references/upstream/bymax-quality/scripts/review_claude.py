"""Reviewer adapter layer: a fresh, read-only Claude CLI pass for a Codex orchestrator."""
import argparse
import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path
import subprocess

import review_prepush
from review_codex import MOVED, unmoved


ERROR_LINE = re.compile(r'^\s*(?:ERROR\s*:|API\s+Error\s*:|claude:\s*error\s*:)', re.I)
AUTH_LINE = re.compile(r'^(?:not logged in|please (?:log|sign) in|unauthorized|invalid api key|no credentials|authentication (?:failed|error))\b', re.I)
QUOTA_LINE = re.compile(
    r"^(?:you(?:'ve| have) (?:hit|reached) your (?:usage |daily |weekly |monthly |5-hour )?limit|"
    r"(?:claude(?: ai)? )?(?:your )?usage limit (?:reached|exceeded)|"
    r"(?:5-hour|weekly|daily|monthly|session) limit (?:reached|exceeded)|insufficient_quota\b|"
    r"(?:you have )?exceeded your current quota\b|quota exceeded\b|"
    r"(?:your )?credit balance is too low\b|out of credits\b|"
    r"purchase more credits\b|billing hard limit\b|payment required\b)", re.I)


def error_payload(text):
    """Read only an actual error message, excluding prompt and structured report prose."""
    text = ERROR_LINE.sub('', text.strip()).strip()
    text = re.sub(r'^\d{3}\s*', '', text).strip()
    if text.startswith('{'):
        try:
            error = json.loads(text).get('error')
            if isinstance(error, dict):
                kind = error.get('type')
                if kind in ('authentication_error', 'permission_error'):
                    return 'authentication failed'
                if kind in ('rate_limit_error', 'overloaded_error'):
                    return ''
                return 'insufficient_quota' if kind == 'insufficient_quota' else str(error.get('message') or '')
        except (ValueError, AttributeError):
            return ''
    return text.replace('’', "'")


def claude_verdict(envelope, stderr):
    """Classify quota only from a CLI error envelope or anchored terminal error lines."""
    messages = [line for line in stderr.splitlines()[-30:] if ERROR_LINE.match(line)]
    if isinstance(envelope, dict) and envelope.get('is_error') is True:
        if envelope.get('subtype') in ('error_max_budget_usd', 'error_max_turns'):
            return 'failed', ''
        if isinstance(envelope.get('result'), str):
            messages.append(envelope['result'])
    payloads = [error_payload(message) for message in messages]
    if any(AUTH_LINE.match(payload) for payload in payloads):
        return 'auth', ''
    quotas = [payload for payload in payloads if QUOTA_LINE.match(payload)]
    return ('quota', quotas[0][:400]) if quotas else ('failed', '')


def reusable_waiver(flow, state):
    """Reuse only this candidate's measured quota waiver while no Codex waiver applies."""
    waiver = state.get('claude_waiver')
    return (isinstance(waiver, dict) and flow.claude_waiver_ok(waiver)
            and waiver.get('head') == state['head']
            and waiver.get('round') == state.get('round', 1)
            and not review_prepush.waiver_ok(state.get('codex_waiver')))


def waive(directory, flow, state, detail, log, binary):
    """Write runtime-measured quota evidence without fabricating a Claude review."""
    waiver = dict(reason='quota', at=int(time.time()), detail=detail, log=str(log),
                  binary=binary, head=state['head'], round=state.get('round', 1))
    flow.require(flow.claude_waiver_ok(waiver), 'Claude changed during the quota probe; run the review again.')
    with flow.locked(directory):
        latest = flow.read_state(directory)
        flow.current(latest)
        flow.require(unmoved(latest, state), MOVED)
        flow.require('claude' not in latest['reviews'], 'Reuse the completed Claude review.')
        flow.require(not review_prepush.waiver_ok(latest.get('codex_waiver')),
                     'Both reviewers are unavailable; no substitute can clear this candidate.')
        latest['claude_waiver'] = waiver
        latest['cleared'] = False
        flow.save(directory, latest)
    print('Claude quota is exhausted; run `review_flow.py codex --as '
          + flow.CLAUDE_SUBSTITUTE + '` for an independent second Codex review. '
          'Report this substitution to the user.', file=sys.stderr)
    return latest


def read_envelope(raw):
    """Decode the CLI envelope without treating incomplete output as a report."""
    try:
        return json.loads(raw.read_text())
    except ValueError:
        return None


def quota_outcome(directory, flow, state, reviewer, envelope, log, raw, binary, returncode):
    """Keep every non-quota failure closed, including setup and substitute failures."""
    if (returncode == 0 and isinstance(envelope, dict) and not envelope.get("is_error")
            and isinstance(envelope.get("structured_output"), dict)):
        return None
    verdict, detail = claude_verdict(envelope, log.read_text(errors='replace'))
    flow.require(verdict != 'auth', 'Claude authentication failed; restore sign-in and run the review again.')
    if verdict != 'quota' or reviewer != 'claude':
        return None
    evidence = raw if isinstance(envelope, dict) and envelope.get('is_error') is True else log
    return waive(directory, flow, state, detail, evidence, binary)


def reserve(directory, flow, reviewer, opening):
    """Reserve a bounded attempt for this Claude pass while keeping the state lock short-lived.

    Each pass has its own budget: the substitute for a waived Codex is a second reviewer,
    not a retry of the first, and spending one another's attempts would let a campaign
    reach two reports from a single reading.
    """
    with flow.locked(directory):
        state = flow.read_state(directory)
        flow.current(state)
        flow.require(reviewer not in state['reviews'], 'Reuse the completed ' + reviewer + ' report.')
        attempts = reviewer.replace('-', '_') + '_attempts'
        flow.require(state.get(attempts, 0) < 2, reviewer + ' retry budget exhausted; preserve both logs.')
        flow.require(unmoved(state, opening), MOVED)
        state[attempts] = state.get(attempts, 0) + 1
        flow.save(directory, state)
        return state, attempts


def command(schema, binary="claude"):
    """Expose only file-reading tools; disable hooks, skills and external MCP tools."""
    return [binary, '-p', '--output-format', 'json', '--json-schema', schema,
            '--tools', 'Read,Grep,Glob', '--allowedTools', 'Read,Grep,Glob',
            '--disable-slash-commands', '--no-session-persistence', '--max-turns', '20',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--settings', '{"disableAllHooks":true}']


def execute(directory, owner_fd, flow, reviewer):
    """Supply the frozen diff and record only a completed matching structured report.

    The task is built and the substitute checked before the attempt is reserved:
    flow.prompt() raises when the declared gates have not passed, and record refuses the
    substitute without a waiver the runtime's own probe wrote. Reserving first spent an attempt on a
    refusal no reviewer ever saw. The predicates are the runtime's, called here rather than copied.
    """
    opening = flow.read_state(directory)
    flow.current(opening)
    if reviewer == "claude" and reusable_waiver(flow, opening):
        return opening
    flow.substitute_allowed(opening, reviewer)
    task = (flow.prompt(opening, directory) + '\nThe caller supplied this exact committed diff below. '
            'You have Read/Grep/Glob only; inspect surrounding files with those tools, not Bash.\n'
            + flow.git_raw('diff', '--no-ext-diff', '--no-textconv', opening['review_base'], opening['head'], '--'))
    binary = review_prepush.resolve_claude()
    flow.require(binary is not None, "Claude is not installed; restore the CLI. Absence is never waived.")
    state, attempts = reserve(directory, flow, reviewer, opening)
    target = directory / f"{reviewer}-{state['round']}-{state[attempts]}.json"
    log = target.with_suffix('.log')
    schema = Path(__file__).with_name('review-report.schema.json').read_text()
    raw = target.with_suffix('.output.json')
    with raw.open('w') as output, log.open('w') as errors:
        result = subprocess.run(command(schema, binary), input=flow.for_a_reader(task), text=True, encoding='utf-8', stdout=output,
                                stderr=errors, timeout=600, pass_fds=(owner_fd,))
    envelope = read_envelope(raw)
    waived = quota_outcome(directory, flow, state, reviewer, envelope, log, raw, binary, result.returncode)
    if waived is not None:
        return waived
    flow.require(result.returncode == 0, reviewer + ' failed; inspect ' + str(log))
    flow.require(isinstance(envelope, dict) and not envelope.get('is_error'), 'Claude returned an error.')
    report = envelope.get('structured_output')
    flow.require(isinstance(report, dict), 'Claude returned no structured review; inspect ' + str(log))
    target.write_text(json.dumps(report, indent=2) + '\n')
    with flow.locked(directory):
        latest = flow.read_state(directory)
        flow.record(argparse.Namespace(reviewer=reviewer, report=str(target)), directory, latest)
        return latest


def run(directory, flow, reviewer='claude'):
    """Serialize Claude runs separately from Codex and ordinary state writers.

    One lock per pass, so the substitute for a waived Codex may run beside the first
    reviewer rather than behind it.
    """
    flow.require(not os.environ.get('CLAUDECODE'),
                 'Inside Claude, let the orchestrator use a fresh reviewer subagent; do not nest Claude CLI.')
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (reviewer + '.lock')).open('w') as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(reviewer + ' is already running; wait for its result.') from error
        return execute(directory, owner.fileno(), flow, reviewer)
