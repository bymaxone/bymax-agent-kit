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
    """Refuse, carrying the reason on the exception.

    The status a refusal exits with is decided at the process boundary and not here: main()
    below, and review_flow's own `matrix` dispatch, each turn this into the 2 that every other
    refusal in the toolkit uses. It used to reach the shell as `SystemExit(message)`, which
    exits 1 — so the matrix refused in a class of its own, a caller keying on 2 for BLOCKED
    read a surviving mutant as a different kind of failure, and the suite's helper, which
    asserts 2, could not drive these refusals through the CLI at all.
    """
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


def per_row(rows):
    """The count each row of an enumeration's stdout states, or None where it states none.

    `grep -c` prints `path:N`, so the count is the last colon-separated field. `wc -l` prints
    `N path` with no separator, so it is a digit token in the row. Reading only the suffix
    refused `wc -l <file>` with a message saying it had answered nothing; reading EVERY digit
    token and adding them took the digits inside the paths `grep -c` prints and answered 3
    for 1; reading the first FIELD read nothing from `cases 4`, a count printed last, and
    refused it as no count at all.

    So: the last colon-separated field where that field is a number, and the first digit token
    of the row otherwise. Every separator-less producer measured here prints the count first.
    A row stating two bare numbers of which the count is not the first — `wc -l 42` is the
    shape — is read wrong, and that is a STATED gap rather than a guarded one, because nothing
    in the row says which number is the answer.
    """
    out = []
    for row in rows:
        tail = row.rsplit(':', 1)[-1].strip()
        if tail.isdigit():
            out.append(int(tail))
            continue
        digits = [word for word in row.split() if word.isdigit()]
        out.append(int(digits[0]) if digits else None)
    return out


def without_total(rows, got):
    """`wc -l a b` appends an aggregate row, and adding it answered 8 for 4 on a real rule.

    It is dropped by what MAKES it an aggregate — the last row of a multi-file run, labelled
    `total`, holding the sum of the rows above it — and never by the label alone. `wc -l total`
    is a one-row run over a file named `total`, and a version matching the label discarded its
    real count and then refused the rule for having answered nothing: a gate refusing a command
    that answered, which is worse than no gate.

    The gap left is STATED: in a multi-file run, a file named `total` listed last whose length
    equals the sum of all the others is read as the aggregate. That under-counts, and an
    under-count is the direction that lets a short mutant list through.
    """
    if len(rows) < 2 or rows[-1].split()[-1] != 'total':
        return got
    above = [n for n in got[:-1] if n is not None]
    if got[-1] is not None and len(above) == len(got) - 1 and got[-1] == sum(above):
        return got[:-1]
    return got


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
    rows = [row.strip() for row in done.stdout.split('\n') if row.strip()]
    counted = [n for n in without_total(rows, per_row(rows)) if n is not None]
    if done.returncode != 0 or not counted:
        bail('Rule %r: its enumeration command produced no count (exit %d). A command that '
             'answers nothing is not an enumeration: %s' % (rule.get('rule'), done.returncode, how))
    # The total, not the largest. `grep -c pattern one.py two.py` prints a count per file, and
    # taking the maximum under-counted every multi-file rule — measured on this delta's own
    # cwd rule, which enumerated 2 against 3 real call sites, so the short-by-N refusal never
    # fired and the third site shipped with no mutant.
    return sum(counted)


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
        seen = set()
        for mutant in mutants:
            key = (mutant.get('file'), mutant.get('anchor'), mutant.get('becomes'), mutant.get('case'))
            # Refused: a repeated entry satisfies the enumeration's count while running
            # the case it already ran, and 'all caught' then covers a case nothing exercised.
            # The case is part of the identity: the same mutation under another case is
            # another measurement, and refusing it blocked a legitimate matrix.
            if key in seen:
                bail('Rule %r repeats a mutant of %s at %r under case %r: a duplicate counts '
                     'toward the enumeration and exercises nothing new.'
                     % (rule.get('rule'), mutant.get('file'), (mutant.get('anchor') or '')[:40],
                        mutant.get('case')))
            seen.add(key)
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


def digest(root, names):
    """One digest over these files, names and bytes, in a fixed order."""
    total = hashlib.sha256()
    for name in sorted(names):
        # Each field hashed to a fixed width before it joins the stream. Appending the
        # bytes directly let a name's tail and a content's head trade places — `a`+`bc`
        # and `ab`+`c` were one digest — and no digest strength repairs a moved boundary.
        total.update(hashlib.sha256(name.encode()).digest())
        total.update(hashlib.sha256((Path(root) / name).read_bytes()).digest())
    return total.hexdigest()


def fingerprint(root, spec):
    """Bind a record to the tree it was measured on: the head, the files the matrix mutated,
    and a digest of their contents that matrix_first recomputes before trusting the record.
    The names travel with the record because a digest nobody can recompute binds nothing."""
    head = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    names = sorted({m['file'] for rule in spec for m in (rule.get('mutants') or [])})
    return head, names, digest(root, names)


def record(root, spec_path, files, out=None):
    """Run the matrix and write what happened; a survivor is a failure, not a note."""
    spec = json.loads(Path(spec_path).read_text())
    if not isinstance(spec, list) or not spec:
        bail('A matrix is a non-empty list of rules.')
    results = matrix(root, spec, files)
    survivors = [r for r in results if not r['caught']]
    head, names, tree = fingerprint(root, spec)
    payload = {'head': head, 'tree': tree, 'files': names, 'rules': len(spec),
               'mutants': len(results), 'survivors': [r['case'] for r in survivors],
               'results': results}
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
    try:
        record(str(Path.cwd()), args[0], args[1:], out=out)
    except SystemExit as refused:
        print(refused.code, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
