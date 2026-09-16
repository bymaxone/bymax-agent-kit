"""Reviewer adapter layer: a fresh, read-only Claude CLI pass for a Codex orchestrator."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess


def reserve(directory, flow):
    """Reserve a bounded Claude attempt while keeping the state lock short-lived."""
    with flow.locked(directory):
        state = flow.read_state(directory)
        flow.current(state)
        flow.require('claude' not in state['reviews'], 'Reuse the completed Claude report.')
        flow.require(state.get('claude_attempts', 0) < 2, 'Claude retry budget exhausted; preserve both logs.')
        state['claude_attempts'] = state.get('claude_attempts', 0) + 1
        flow.save(directory, state)
        return state


def command(schema):
    """Expose only file-reading tools; disable hooks, skills and external MCP tools."""
    return ['claude', '-p', '--output-format', 'json', '--json-schema', schema,
            '--tools', 'Read,Grep,Glob', '--allowedTools', 'Read,Grep,Glob',
            '--disable-slash-commands', '--no-session-persistence', '--max-turns', '20',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--settings', '{"disableAllHooks":true}']


def execute(directory, owner_fd, flow):
    """Supply the frozen diff and record only a completed matching structured report."""
    state = reserve(directory, flow)
    target = directory / f"claude-{state['round']}-{state['claude_attempts']}.json"
    log = target.with_suffix('.log')
    schema = Path(__file__).with_name('review-report.schema.json').read_text()
    task = (flow.prompt(state) + '\nThe caller supplied this exact committed diff below. '
            'You have Read/Grep/Glob only; inspect surrounding files with those tools, not Bash.\n'
            + flow.git_raw('diff', '--no-ext-diff', '--no-textconv', state['review_base'], state['head'], '--'))
    raw = target.with_suffix('.output.json')
    with raw.open('w') as output, log.open('w') as errors:
        result = subprocess.run(command(schema), input=task, text=True, stdout=output,
                                stderr=errors, timeout=600, pass_fds=(owner_fd,))
    flow.require(result.returncode == 0, 'Claude failed; inspect ' + str(log))
    envelope = json.loads(raw.read_text())
    flow.require(isinstance(envelope, dict) and not envelope.get('is_error'), 'Claude returned an error.')
    report = envelope.get('structured_output')
    flow.require(isinstance(report, dict), 'Claude returned no structured review; inspect ' + str(log))
    target.write_text(json.dumps(report, indent=2) + '\n')
    with flow.locked(directory):
        latest = flow.read_state(directory)
        flow.record(argparse.Namespace(reviewer='claude', report=str(target)), directory, latest)
        return latest


def run(directory, flow):
    """Serialize Claude runs separately from Codex and ordinary state writers."""
    flow.require(not os.environ.get('CLAUDECODE'),
                 'Inside Claude, let the orchestrator use a fresh reviewer subagent; do not nest Claude CLI.')
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'claude.lock').open('w') as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Claude is already running; wait for its result.') from error
        return execute(directory, owner.fileno(), flow)
