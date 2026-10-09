"""Reviewer adapter layer: an independent Codex pass replacing a quota-exhausted Claude.

The ordinary Codex reviewer and this pass own separate locks, attempts and files.
No orchestrator or implementer report can stand in for the fresh CLI session.
"""
import argparse
import fcntl
from pathlib import Path
import subprocess

from review_codex import escalation, unmoved, MOVED
from review_prepush import resolve_codex


def reserve(directory, flow, opening):
    """Reserve one of two attempts against unchanged gates and the quota-bound candidate."""
    with flow.locked(directory):
        state = flow.read_state(directory)
        flow.current(state)
        flow.substitute_allowed(state, flow.CLAUDE_SUBSTITUTE)
        flow.require(flow.CLAUDE_SUBSTITUTE not in state['reviews'], 'Reuse the completed codex-b report.')
        flow.require(state.get('codex_b_attempts', 0) < 2, 'codex-b retry budget exhausted; preserve both logs.')
        flow.require(unmoved(state, opening), MOVED)
        state['codex_b_attempts'] = state.get('codex_b_attempts', 0) + 1
        flow.save(directory, state)
        return state


def execute(directory, owner_fd, flow):
    """Run a read-only ephemeral review and accept only a matching complete structured report."""
    opening = flow.read_state(directory)
    flow.substitute_allowed(opening, flow.CLAUDE_SUBSTITUTE)
    task = flow.prompt(opening, directory)
    binary = resolve_codex()
    flow.require(binary is not None, 'Codex is unavailable; Claude cannot be substituted.')
    state = reserve(directory, flow, opening)
    report = directory / f"codex-b-{state['round']}-{state['codex_b_attempts']}.json"
    schema = directory / 'report-schema.json'
    schema.write_text(Path(__file__).with_name('review-report.schema.json').read_text())
    command = [binary, 'exec', *escalation(state), '-c', 'approval_policy="never"', '--sandbox',
               'read-only', '--ephemeral', '--output-schema', str(schema),
               '--output-last-message', str(report), '-']
    with report.with_suffix('.log').open('w') as output:
        result = subprocess.run(command, input=flow.for_a_reader(task), text=True, encoding='utf-8',
                                stdout=output, stderr=subprocess.STDOUT, timeout=600, pass_fds=(owner_fd,))
    flow.require(result.returncode == 0, 'codex-b failed; preserve its log. Both required reviews must complete.')
    with flow.locked(directory):
        latest = flow.read_state(directory)
        flow.require(unmoved(latest, state), MOVED)
        flow.record(argparse.Namespace(reviewer=flow.CLAUDE_SUBSTITUTE, report=str(report)), directory, latest)
        return latest


def run(directory, flow):
    """Hold the substitute's own process lock without blocking the primary Codex reviewer."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'codex-b.lock').open('w') as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('codex-b is already running; wait for its result.') from error
        return execute(directory, owner.fileno(), flow)
