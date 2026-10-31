"""Interface layer: the campaign's command-line surface and the reviewer identities it accepts.

review_flow imports this module, so nothing here imports review_flow. The parser only declares
arguments; what each one means is enforced where the action runs.
"""
import argparse

# The second Claude pass that stands in for a waived Codex, and the second Codex pass that stands
# in for a quota-exhausted Claude.
SUBSTITUTE = 'claude-b'
CLAUDE_SUBSTITUTE = 'codex-b'


def reviewer_parsers(sub):
    """Declare both provider adapters and quota-bound substitute report identities."""
    cod = sub.add_parser('codex')
    cod.add_argument('--as', dest='reviewer', choices=('codex', CLAUDE_SUBSTITUTE), default='codex')
    pas = sub.add_parser('claude')
    pas.add_argument('--as', dest='reviewer', choices=('claude', SUBSTITUTE), default='claude',
                     help='Which Claude pass this run is: the first, or the substitute for a waived Codex.')
    rec = sub.add_parser('record')
    rec.add_argument('--reviewer', choices=('claude', SUBSTITUTE, 'codex', CLAUDE_SUBSTITUTE), required=True)
    rec.add_argument('--report', required=True)


def start_parser(sub):
    """Declare `start` and the reasons a round may be asked to record."""
    begin = sub.add_parser('start')
    begin.add_argument('--autonomous', action='store_true',
                       help='Enroll shipping work in a six-candidate budget shared across pushes on this branch.')
    begin.add_argument('--base', required=True)
    begin.add_argument('--context', help='Required except with --rebased-from, which keeps the frozen one.')
    begin.add_argument('--rebased-from', default='', metavar='SHA',
                       help='The head this campaign froze, when the branch was rebased onto a moved base.')
    begin.add_argument('--probe', help='Correction rounds: JSON list of {command, expected, observed}.')
    begin.add_argument('--design-round', action='store_true',
                       help='Acknowledge a reopened finding and review the approach, not the instance.')
    begin.add_argument('--no-regression-reason', default='',
                       help='Correction rounds that touch no test: why a regression is infeasible.')
    begin.add_argument('--nit-round', default='',
                       help='Spend a round on P3 findings anyway: why, shown to both reviewers.')
    begin.add_argument('--widen-scope', default='',
                       help='Touch a file no open finding names: why, shown to both reviewers.')
    begin.add_argument('--base-branch', default='',
                       help='The branch this work merges into, such as origin/main: what a commit '
                            'reachable from it did not write, whatever line it sits on.')
    begin.add_argument('--base-branch-file', default='',
                       help='A file whose first line is the base branch, as push writes one.')
    begin.add_argument('--after-archived', default='',
                       help='Start a campaign after an unfinished one: who authorised it, for what scope.')
    begin.add_argument('--answers', nargs='+', action='extend', metavar='PATH:SLUG',
                       help='After a cleared candidate: the external findings this correction answers.')
    begin.add_argument('--extend-delivery', default='',
                       help='Continue past a spent delivery budget: who authorised it, and why.')
    begin.add_argument('--correct-checks', default='',
                       help='Replace declared gates that were wrong, changing nothing else: why, '
                            'recorded in the ledger and shown to both reviewers.')


def parser(description):
    """Define the small explicit campaign lifecycle CLI."""
    cli = argparse.ArgumentParser(description=description)
    sub = cli.add_subparsers(dest='action', required=True)
    start_parser(sub)
    for action in ('status', 'prompt', 'finish', 'codex-check', 'range', 'lessons', 'outcomes'):
        sub.add_parser(action)
    reviewer_parsers(sub)
    tri = sub.add_parser('triage')
    tri.add_argument('--report', required=True)
    gate = sub.add_parser('check')
    gate.add_argument('command', nargs=argparse.REMAINDER)
    mut = sub.add_parser('matrix')
    mut.add_argument('--spec', required=True, help='the matrix: rules, their enumeration, their mutants')
    mut.add_argument('paths', nargs='+', help='test paths the cases live in')
    pro = sub.add_parser('prose')
    pro.add_argument('--base', default='', help='the merge-base the pass reads the delta from; '
                     'unneeded while a correction is being prepared')
    pro.add_argument('--stage', choices=('run', 'prepare', 'verify'), default='run',
                     help='run: the CLI does it all; prepare/verify: a subagent does the editing')
    return cli
