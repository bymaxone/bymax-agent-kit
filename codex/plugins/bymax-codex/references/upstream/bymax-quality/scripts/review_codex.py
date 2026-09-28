#!/usr/bin/env python3
"""Codex adapter layer: run the independent Codex pass on a bounded attempt budget, and turn a
Codex this machine cannot run into a waiver its own probe measured.

Every function that reads or writes campaign state takes `flow`, the runtime module, and calls
back through it (flow.locked, flow.read_state, flow.prompt, flow.record, ...) rather than
importing review_flow: the runtime passes itself, as it does to review_claude, so a caller that
replaces one of its functions reaches this path too, and nothing here has to be restated.
"""
import argparse
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from review_git import for_a_reader, require
from review_prepush import CODEX_LOCATIONS, WAIVER_TTL, resolve_codex, waiver_ok


BUDGET_SPENT = (
    'Codex retry budget exhausted: the helper will not run Codex again on this candidate. Report '
    'the failure with both attempt logs; if a human authorises starting over, rename this '
    'state directory keeping its whole current name and adding to it, delete nothing, and '
    'start a new '
    'campaign covering the same commits. A completed Codex report obtained outside the helper may still be recorded; an '
    'incomplete one never advances a round.')


def reserve_codex(directory, flow, opening=None):
    """Reserve one attempt without holding the lock throughout model execution."""
    with flow.locked(directory):
        state = flow.read_state(directory)
        flow.current(state)
        require('codex' not in state['reviews'], 'Reuse the completed Codex review.')
        require(state.get('codex_attempts', 0) < 2, BUDGET_SPENT)
        require(opening is None or unmoved(state, opening), MOVED)
        state['codex_attempts'] = state.get('codex_attempts', 0) + 1
        state['codex_running'] = True
        flow.save(directory, state)
        return state


# Asked under the lock that reserves the attempt, before it is counted: the task was built from
# `opening`, and a check recorded since then may have failed, or be running, which the task
# would tell a reviewer had passed.
MOVED = 'The campaign moved, or a gate ran while this review was being prepared; run it again.'


def unmoved(state, opening):
    """Whether the campaign is still the one a review task was built from."""
    return all(state.get(key) == opening.get(key) for key in ('head', 'round', 'review_base', 'checks'))


def spent(directory, flow):
    """The candidate's state when its Codex attempts are gone, or None while one is left."""
    with flow.locked(directory):
        state = flow.read_state(directory)
        flow.current(state)
        require('codex' not in state['reviews'], 'Reuse the completed Codex review.')
        return state if state.get('codex_attempts', 0) >= 2 else None


# Codex prints its fatal reason on lines of its own, and the whole review prompt is echoed
# into the same log. Only these lines are classified, and only near the end: a review whose
# own context discusses a usage limit would otherwise read as one and waive the reviewer it
# was meant to run. Anything unmatched stays a failure, which is the blocking answer.
ERROR_LINE = re.compile(r'^\s*(?:ERROR\b|error:|stream error|codex:\s*error)', re.IGNORECASE)
ERROR_TAIL = 30
# An account with nothing left to spend. Transient rate limiting is deliberately absent:
# that is a reason to retry, not a reviewer this machine cannot run.
QUOTA_SIGNS = ('usage limit', 'insufficient_quota', 'exceeded your current quota', 'quota exceeded',
               'purchase more credits', 'out of credits', 'credit balance is too low',
               'billing hard limit', 'payment required')
# Setup, not absence: one command fixes it, and waiving it would make deleting a single
# credentials file a universal bypass of the receipt rule.
AUTH_SIGNS = ('not logged in', 'codex login', 'please log in', 'please sign in', 'unauthorized',
              'invalid api key', 'no credentials', 'authentication failed', 'authentication error')


def codex_verdict(text):
    """Classify a failed Codex run from the error lines it ended with.

    Returns (verdict, detail): `quota` is waivable, `auth` is setup the caller must fix,
    and `failed` — including a run that printed no error line at all — is what it has
    always been, a review that did not happen.
    """
    tail = [line.strip() for line in text.splitlines() if line.strip()][-ERROR_TAIL:]
    errors = [line for line in tail if ERROR_LINE.match(line)]
    detail, joined = ' | '.join(dict.fromkeys(errors))[:400], ' '.join(errors).lower()
    if not errors:
        return 'failed', ''
    if any(sign in joined for sign in AUTH_SIGNS):
        return 'auth', detail
    if any(sign in joined for sign in QUOTA_SIGNS):
        return 'quota', detail
    return 'failed', detail


def waive(directory, flow, state, reason, detail, log, binary):
    """Record what this runtime's own probe found about Codex on this machine.

    Written here and nowhere else. No flag, argument or reviewer report the caller passes
    can produce a waiver, and nobody honours one on trust: this runtime, the Bash guard and
    the pre-push hook each re-run the same probe against the machine in front of them. A
    waiver that does not already describe this one is refused rather than stored, so a
    campaign never clears on a reason the hook would reject at push time.
    """
    waiver = dict(reason=reason, at=int(time.time()), detail=detail,
                  log=str(log), binary=binary, head=state['head'])
    require(waiver_ok(waiver),
            'This probe produced a waiver that does not describe this machine, so it is not '
            'recorded: Codex changed underneath the run. Run `review_flow.py codex` again.')
    with flow.locked(directory):
        latest = flow.read_state(directory)
        flow.current(latest)
        require('codex' not in latest['reviews'], 'Codex already reviewed this candidate.')
        latest['codex_waiver'] = waiver
        latest['cleared'] = False
        flow.save(directory, latest)
    print('Codex was waived on this candidate (' + reason + '): ' + (detail or 'not installed')
          + '. The second review is ' + flow.SUBSTITUTE + ': run the generated prompt in a second '
          'fresh-context reviewer subagent that shares nothing with the first, and record its '
          'report with --reviewer ' + flow.SUBSTITUTE + '. Say so in the report to the user.', file=sys.stderr)
    return latest


def codex_outcome(directory, flow, state, log, binary):
    """Turn a failed Codex run into a waiver, a setup instruction, or the failure it is."""
    verdict, detail = codex_verdict(log.read_text(errors='replace') if log.exists() else '')
    require(verdict != 'auth',
            'Codex is installed at ' + binary + ' but is not signed in, which is setup rather than a '
            'reviewer this machine cannot run: run /bymax-quality:codex-setup and then `review_flow.py '
            'codex` again. This is never waived, because a missing credentials file would otherwise '
            'clear any candidate. Evidence: ' + detail + ' (' + str(log) + ').')
    require(verdict == 'quota', 'Codex failed; inspect ' + str(log))
    return waive(directory, flow, state, 'quota', detail, log, binary)


# Codex layers $CODEX_HOME/<name>.config.toml over its base config for `exec -p <name>`.
# The package names the profile and never the model: the catalog rots — slugs are retired
# within a release or two — and which model is worth escalating to is the user's judgement,
# written once by /bymax-quality:codex-setup. A machine with no such file gets exactly
# today's behaviour, because an absent binding is a choice and not a misconfiguration.
ESCALATED_PROFILE = 'escalated'


def codex_home():
    """Codex's own configuration directory, found the way Codex finds it."""
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')


def escalation(state):
    """`-p <profile>` on the rounds where a better reviewer earns its cost, or nothing.

    Decided from the campaign's own state, never by the caller and never by a model
    remembering to ask: a round this runtime has already declared decisive — the approach
    is under review rather than a patch, a finding came back after a claimed fix, or this
    is the last candidate the budget allows — is where a defect the reviewer misses costs
    the whole delivery. Every other round uses the standing model, which is also what keeps
    the shared quota pool from being spent at the top of the price list.
    """
    frozen = max(state.get('round', 1), state.get('delivery_used', 0))
    decisive = bool(state.get('design_round') or state.get('reopened')
                    or frozen >= state.get('max_rounds', 3))
    if not decisive or not (codex_home() / (ESCALATED_PROFILE + '.config.toml')).is_file():
        return []
    return ['-p', ESCALATED_PROFILE]


# Not a review: no diff, no context, no schema. A live account answers it for a token or
# two; an exhausted one fails the way it always does, which is the answer being asked for.
AVAILABILITY_PROMPT = 'Reply with the single word OK. Do not read files or run commands.\n'
PROBE_BUDGET = 2


def availability(directory, flow, state, owner_fd):
    """Ask whether Codex can run at all, once this candidate's review attempts are gone.

    The budget exists to stop a reviewer being run again; it must not decide, by itself,
    that a machine has a reviewer. An exhausted account is discovered only by spending
    attempts, so the state that most needs a waiver is the one the budget locks out: a
    round that hit the wall and retried, and every campaign frozen before waivers existed.

    This asks the machine now rather than rereading an old log, so credits that came back
    are seen, a Codex uninstalled since is seen, and no file on disk becomes a way to claim
    a reviewer is missing. What it cannot answer is bounded too: the refusals below are the
    same ones a spent budget always gave.
    """
    binary = resolve_codex()
    if binary is None:
        return waive(directory, flow, state, 'absent', '', '', '')
    require(state.get('codex_probes', 0) < PROBE_BUDGET,
            BUDGET_SPENT + ' Its availability probe has also run ' + str(PROBE_BUDGET)
            + ' times on this candidate without a recognisable answer; stop and report that.')
    with flow.locked(directory):
        latest = flow.read_state(directory)
        latest['codex_probes'] = latest.get('codex_probes', 0) + 1
        flow.save(directory, latest)
    log = directory / f"codex-{state['round']}-probe-{state.get('codex_probes', 0) + 1}.log"
    with log.open('w') as output:
        result = subprocess.run([binary, 'exec', '-c', 'approval_policy="never"', '--sandbox',
                                 'read-only', '--ephemeral', '-'],
                                input=AVAILABILITY_PROMPT, text=True, stdout=output,
                                stderr=subprocess.STDOUT, timeout=120, pass_fds=(owner_fd,))
    verdict, detail = codex_verdict(log.read_text(errors='replace'))
    require(result.returncode != 0,
            BUDGET_SPENT + ' Codex answered an availability probe just now, so the account is not '
            'the problem and there is nothing to waive: the two attempts failed for another reason, '
            'and that reason is what to report.')
    require(verdict != 'auth',
            'Codex is installed at ' + binary + ' but is not signed in, which is setup rather than a '
            'reviewer this machine cannot run: run /bymax-quality:codex-setup, then `review_flow.py '
            'codex` again. Evidence: ' + detail + ' (' + str(log) + ').')
    require(verdict == 'quota', BUDGET_SPENT + ' Its availability probe failed for a reason nobody '
            'recognises, so nothing is waived; inspect ' + str(log) + '.')
    return waive(directory, flow, state, 'quota', detail, log, binary)


def codex_review(directory, flow):
    """Hold a separate OS lock, released on exit, without blocking Claude's writer."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'codex.lock').open('w') as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Codex is already running; wait for its shell result.') from error
        return execute_codex(directory, owner.fileno(), flow)


def execute_codex(directory, owner_fd, flow):
    """Consume a bounded attempt; let the child retain ownership if the parent dies.

    A Codex this machine has no way to run is not a review that failed: the probe that
    established that records a waiver and the campaign continues on the substitute pair.
    Everything else a run can do — time out, crash, return an incomplete report, print an
    error nobody recognises — is still a review that did not happen. With the attempts
    already spent there is no review left to run, and the question that remains — whether
    this machine has a reviewer at all — is answered by an availability probe instead.
    """
    opening = flow.read_state(directory)
    flow.gate_first(opening, directory)   # before the attempt is reserved, never after
    exhausted = spent(directory, flow)
    if exhausted is not None:
        return availability(directory, flow, exhausted, owner_fd)
    # Built before the attempt is reserved: prompt() runs the gates again, and a collect that
    # fails the second time would otherwise spend the attempt on a review nobody ran.
    task = flow.prompt(opening, directory)
    state = reserve_codex(directory, flow, opening)
    try:
        binary = resolve_codex()
        if binary is None:
            waive(directory, flow, state, 'absent', '', '', '')
        else:
            run_codex(directory, flow, state, task, binary, owner_fd)
    finally:
        with flow.locked(directory):
            latest = flow.read_state(directory)
            if all(latest.get(key) == state.get(key) for key in ('head', 'round', 'codex_attempts')):
                latest['codex_running'] = False
                flow.save(directory, latest)
    return latest


def run_codex(directory, flow, state, task, binary, owner_fd):
    """One read-only Codex pass over the task, recorded when it completes. The binary is the
    resolved absolute path, never the bare name: the binary a waiver names must be the installed
    one, not whatever a single command's $PATH pointed at."""
    report = directory / f"codex-{state['round']}-{state['codex_attempts']}.json"
    log = report.with_suffix('.log')
    schema = directory / 'report-schema.json'
    schema.write_text(Path(__file__).with_name('review-report.schema.json').read_text())
    profile = escalation(state)
    if profile:
        print('Decisive round: this Codex pass uses the ' + ESCALATED_PROFILE
              + ' profile from ' + str(codex_home()) + '.', file=sys.stderr)
    command = [binary, 'exec', *profile, '-c', 'approval_policy="never"', '--sandbox',
               'read-only', '--ephemeral', '--output-schema', str(schema),
               '--output-last-message', str(report), '-']
    with log.open('w') as output:
        result = subprocess.run(command, input=for_a_reader(task), text=True, encoding='utf-8',
                                stdout=output, stderr=subprocess.STDOUT, timeout=600, pass_fds=(owner_fd,))
    if result.returncode == 0:
        with flow.locked(directory):
            latest = flow.read_state(directory)
            flow.record(argparse.Namespace(reviewer='codex', report=str(report)), directory, latest)
    else:
        codex_outcome(directory, flow, state, log, binary)


def codex_check():
    """Report what the availability probe sees, spending neither an attempt nor a token.

    The same resolution every consumer of a waiver runs, exposed so a human can see why
    one was granted or refused without reading state by hand.
    """
    binary = resolve_codex()
    profile = codex_home() / (ESCALATED_PROFILE + '.config.toml')
    return dict(installed=bool(binary), binary=binary or '', on_path=shutil.which('codex') or '',
                searched=list(CODEX_LOCATIONS), waiver_ttl_hours=WAIVER_TTL // 3600,
                waivable=['absent', 'quota'], never_waived=['auth', 'failed'],
                codex_home=str(codex_home()), escalated_profile=str(profile),
                escalation_bound=profile.is_file())
