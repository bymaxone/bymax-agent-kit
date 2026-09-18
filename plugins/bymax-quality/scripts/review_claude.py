"""Reviewer adapter layer: a fresh, read-only Claude CLI pass for a Codex orchestrator."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess


def reserve(directory, flow, reviewer):
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
        state[attempts] = state.get(attempts, 0) + 1
        flow.save(directory, state)
        return state, attempts


def command(schema):
    """Expose only file-reading tools; disable hooks, skills and external MCP tools."""
    return ['claude', '-p', '--output-format', 'json', '--json-schema', schema,
            '--tools', 'Read,Grep,Glob', '--allowedTools', 'Read,Grep,Glob',
            '--disable-slash-commands', '--no-session-persistence', '--max-turns', '20',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--settings', '{"disableAllHooks":true}']


def execute(directory, owner_fd, flow, reviewer):
    """Supply the frozen diff and record only a completed matching structured report.

    Two things are checked before the attempt is reserved, for the same reason: flow.prompt()
    raises when the declared gates have not passed, and record refuses the substitute without a
    waiver the runtime's own probe wrote. Reserving first spent an attempt on a refusal no
    reviewer ever saw. Both predicates are the runtime's, called here rather than copied.
    """
    opening = flow.read_state(directory)
    flow.gate_first(opening)
    flow.substitute_allowed(opening, reviewer)
    state, attempts = reserve(directory, flow, reviewer)
    target = directory / f"{reviewer}-{state['round']}-{state[attempts]}.json"
    log = target.with_suffix('.log')
    schema = Path(__file__).with_name('review-report.schema.json').read_text()
    task = (flow.prompt(state) + '\nThe caller supplied this exact committed diff below. '
            'You have Read/Grep/Glob only; inspect surrounding files with those tools, not Bash.\n'
            + flow.git_raw('diff', '--no-ext-diff', '--no-textconv', state['review_base'], state['head'], '--'))
    raw = target.with_suffix('.output.json')
    with raw.open('w') as output, log.open('w') as errors:
        result = subprocess.run(command(schema), input=task, text=True, stdout=output,
                                stderr=errors, timeout=600, pass_fds=(owner_fd,))
    flow.require(result.returncode == 0, reviewer + ' failed; inspect ' + str(log))
    envelope = json.loads(raw.read_text())
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
