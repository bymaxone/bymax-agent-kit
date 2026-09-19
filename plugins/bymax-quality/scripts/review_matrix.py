#!/usr/bin/env python3
"""Run a mutation matrix and record what happened, instead of being told what happened.

The suite proves the code does what the tests say. It cannot prove the tests discriminate: a
vacuous gate passes its own suite by definition. The only thing that catches one is mutating
what it guards and watching a named case fail — and until now that step was the author's word.
`--probe` takes free text, so "observed: the mutant fails the case" is a sentence, not a
measurement. Measured on two repositories: an author wrote an `observed` for a command never
run (a reviewer ran it: it returned None), and this package's own memory records a run that
printed `69 passed` while no mutant had been applied at all, because the anchor matched twice
and the mutation was skipped.

So the runtime runs it. Three things are checked that an author's report cannot establish:

    applicable   the anchor occurs exactly once in the file at HEAD. Zero means the mutation
                 never landed; more than one means nobody knows which line was mutated.
    meaningful   the case passes on the clean tree first. "It fails with the mutant" says
                 nothing when it fails without one, and that direction reads as success.
    caught       the case fails with the mutant applied. A survivor is the finding.

And one thing no runner can check by itself, so it is asked instead: how the case list was
enumerated. Where that rule is a command, the command runs and its count must not exceed the
mutants declared — which is how a list of one for a helper with six call sites stops being a
silent default. Where it is not a command, saying so is required, and that admission is worth
more than the list: a rule that cannot be enumerated mechanically is a mechanism not yet
understood well enough to be corrected.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PYTEST = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider']


def bail(message):
    raise SystemExit('BLOCKED: ' + message)


def caches(root):
    for path in Path(root).rglob('__pycache__'):
        shutil.rmtree(path, ignore_errors=True)


def run_case(root, selector, files):
    """Run one case. CPython invalidates bytecode on (mtime seconds, size), so two mutants of
    the same size inside one second serve the previous one's result — and the direction that
    lies is 'broke nothing', which manufactures a false claim that a rule is uncovered."""
    caches(root)
    done = subprocess.run([*PYTEST, *files, '-k', selector], cwd=root,
                          capture_output=True, text=True,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    tail = done.stdout.strip().splitlines()
    return done.returncode, (tail[-1] if tail else done.stderr[-160:])


def outcome(tail):
    """Whether a run FAILED a case or merely stopped working.

    `exit != 0` cannot tell the two apart, and the difference is the whole measurement: a
    mutant that breaks the import makes every case error, which reads as "caught" while the
    case never ran. Measured on this file's own fixtures — replacing a `def` line with a
    module-scope raise recorded two mutants as caught, and neither case had executed.
    """
    failed = re.search(r'(\d+) failed', tail)
    errored = re.search(r'(\d+) error', tail)
    # An error anywhere means some case did not run, whatever else the line says. Reading
    # "1 failed, 3 errors" as a clean catch was measured: a case that errored in fixture setup
    # was recorded caught, and the three that never ran were invisible.
    if errored:
        return 'error'
    return 'failed' if failed else 'passed'


def enumerated(root, rule):
    """How many cases the rule's own enumeration command says exist, or None when it is not
    a command — which the author must then say in words rather than leave to the default."""
    how = (rule.get('enumeration') or '').strip()
    if not how:
        bail('Rule %r declares no enumeration: say how the case list was derived, as a command '
             'where one exists, or state that no command derives it and why.' % rule.get('rule'))
    if how == 'not derivable by command':
        if not (rule.get('why') or '').strip():
            bail('Rule %r says no command derives its cases and does not say why. That '
                 'admission is the useful half: a rule nothing can enumerate is a mechanism '
                 'not yet understood well enough to correct.' % rule.get('rule'))
        return None
    done = subprocess.run(how, shell=True, cwd=root, capture_output=True, text=True)
    digits = ''.join(c if c.isdigit() else ' ' for c in done.stdout).split()
    if done.returncode != 0 or not digits:
        bail('Rule %r: its enumeration command produced no count (exit %d). A command that '
             'answers nothing is not an enumeration: %s' % (rule.get('rule'), done.returncode, how))
    # The total, not the largest. `grep -c pattern one.py two.py` prints a count per file, and
    # taking the maximum under-counted every multi-file rule — measured on this delta's own
    # cwd rule, which enumerated 2 against 3 real call sites, so the short-by-N refusal never
    # fired and the third site shipped with no mutant.
    return sum(int(d) for d in digits)


def apply_mutant(root, mutant):
    """Put the mutant in place, or say exactly why it could not be applied."""
    path = Path(root) / mutant['file']
    if not path.is_file():
        bail('Mutant for %r names %s, which is not a file here.' % (mutant.get('case'), mutant['file']))
    if not os.access(path, os.W_OK):
        bail('Mutant for %r cannot be applied: %s is not writable, and a matrix that cannot '
             'restore what it changed must not start.' % (mutant.get('case'), mutant['file']))
    text = path.read_text()
    hits = text.count(mutant['anchor'])
    if hits != 1:
        bail('Mutant for %r: its anchor occurs %d times in %s. Zero means the mutation never '
             'landed and the run proves nothing; more than one means nobody knows which line '
             'carried it. This is not a formality — a matrix that printed "69 passed" with no '
             'mutant applied is why the anchor is counted.' % (mutant.get('case'), hits, mutant['file']))
    path.write_text(text.replace(mutant['anchor'], mutant['becomes'], 1))
    return path, text


def one(root, mutant, files, clean=None):
    """Clean run, then mutated run, then restore whatever happens.

    The clean run is a property of the case, not of the mutant, so `clean` carries the answer
    between mutants that share one. Without it a sixteen-mutant matrix pays thirty-two suite
    runs for sixteen measurements, and a matrix nobody can afford to run is a matrix nobody
    runs.
    """
    seen = clean if clean is not None else {}
    if mutant['case'] not in seen:
        seen[mutant['case']] = run_case(root, mutant['case'], files)
    clean_code, clean_tail = seen[mutant['case']]
    if clean_code != 0:
        bail('Case %r does not pass on the clean tree (%s). A mutant that fails a case which '
             'already fails measures nothing.' % (mutant['case'], clean_tail))
    path, original = apply_mutant(root, mutant)
    try:
        code, tail = run_case(root, mutant['case'], files)
    finally:
        path.write_text(original)
        caches(root)
    how = outcome(tail)
    if how == 'error':
        bail('Mutant for %r stopped the tree from loading rather than failing the case (%s). '
             'That is a crash, not a measurement: the case never ran, and every case would '
             'report the same. Mutate what the gate reads, not what the module needs to '
             'import.' % (mutant['case'], tail))
    return {'case': mutant['case'], 'file': mutant['file'], 'caught': how == 'failed', 'saw': tail}


def matrix(root, spec, files):
    """Every rule, every mutant, with a survivor stopping the run."""
    results, clean = [], {}
    for rule in spec:
        declared = enumerated(root, rule)
        mutants = rule.get('mutants') or []
        if not mutants:
            bail('Rule %r declares no mutants.' % rule.get('rule'))
        if declared is not None and declared > len(mutants):
            bail('Rule %r enumerates %d case(s) by its own command and mutates %d. The list is '
                 'short by %d: a case nothing mutates is a case nothing covers.'
                 % (rule.get('rule'), declared, len(mutants), declared - len(mutants)))
        for mutant in mutants:
            result = one(root, mutant, files, clean)
            result['rule'] = rule.get('rule')
            results.append(result)
            print('%-8s %-46s %s' % ('caught' if result['caught'] else 'SURVIVED',
                                     mutant['case'], result['saw']))
    return results


def fingerprint(root, spec):
    """Bind a record to the tree it was measured on, so it cannot be reused for another."""
    head = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    names = sorted({m['file'] for rule in spec for m in (rule.get('mutants') or [])})
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update((Path(root) / name).read_bytes())
    return head, digest.hexdigest()


def record(root, spec_path, files, out=None):
    """Run the matrix and write what happened; a survivor is a failure, not a note."""
    spec = json.loads(Path(spec_path).read_text())
    if not isinstance(spec, list) or not spec:
        bail('A matrix is a non-empty list of rules.')
    results = matrix(root, spec, files)
    survivors = [r for r in results if not r['caught']]
    head, digest = fingerprint(root, spec)
    payload = {'head': head, 'tree': digest, 'rules': len(spec), 'mutants': len(results),
               'survivors': [r['case'] for r in survivors], 'results': results}
    if out:
        Path(out).write_text(json.dumps(payload, indent=2) + '\n')
    if survivors:
        bail('%d mutant(s) survived: %s. A gate nothing can break is decoration, and the survivor '
             'is the finding — fix the gate, or fix the mutant if it never applied, and run again.'
             % (len(survivors), ', '.join(r['case'] for r in survivors)))
    print('\n%d rule(s), %d mutant(s), all caught. Recorded against %s.' % (len(spec), len(results), head[:12]))
    return payload


def main(argv):
    if len(argv) < 3:
        print('usage: review_matrix.py <matrix.json> <test path> [more paths] [--out FILE]',
              file=sys.stderr)
        return 2
    args = list(argv[1:])
    out = None
    if '--out' in args:
        at = args.index('--out')
        if at + 1 >= len(args):
            print('--out needs a path', file=sys.stderr)
            return 2
        out = args[at + 1]
        del args[at:at + 2]
    record(str(Path.cwd()), args[0], args[1:], out=out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
