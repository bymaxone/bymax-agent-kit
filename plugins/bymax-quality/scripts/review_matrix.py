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
import secrets
import signal
import subprocess
import time
import tempfile
import sys
from pathlib import Path

from review_collect import MARK

# A run under a mutant may take this many times its clean run, and never less than FLOOR
# seconds: a mutant that disables a stop condition otherwise leaves pytest waiting forever,
# and the restore that follows it is never reached.
SLACK, FLOOR, CLEAN = 10, 60, 1800
# `-o addopts=` first: a project's own addopts would otherwise reach every pytest this runtime
# starts, and one `-q` more or a `-v` changes the lines the collect and the outcome read.
# The environment's PYTEST_ADDOPTS is the same option by another door, cleared in pytest_env().
PYTEST = [sys.executable, '-m', 'pytest', '-o', 'addopts=', '-q', '-p', 'no:cacheprovider']
# The directory names that mark a test location, compared without case. The campaign's own test
# classifier reads the same names, and a case holds the two together.
TEST_DIRECTORIES = frozenset(('test', 'tests', 'spec', '__tests__'))


def pytest_env():
    """The environment every pytest here runs with: no bytecode written, and no PYTEST_ADDOPTS —
    pytest prepends it as it does the ini's addopts, and it reached the runs and the collects
    when only the ini's was cleared."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTEST_ADDOPTS', None)
    return env


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


def run_case(root, selector, files, deadline=CLEAN):
    """Run one case: the selector over these paths, or with no selector one node id, which
    selects itself. CPython invalidates bytecode on (mtime seconds, size), so two mutants of
    the same size inside one second serve the previous one's result — and the direction that
    lies is 'broke nothing', which manufactures a false claim that a rule is uncovered. So each
    run reads bytecode from an empty directory of its own and writes none, and nothing under
    root is deleted to get there: a file tracked beneath a __pycache__ belongs to the tree.

    Past `deadline` seconds the whole process group is killed, pytest and each child it did not
    detach, and the run reads as timed out.
    """
    args = [*PYTEST, *arguments(root, files)] + (['-k', selector] if selector else [])
    with tempfile.TemporaryDirectory() as empty, \
            subprocess.Popen(args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=dict(pytest_env(), PYTHONPYCACHEPREFIX=empty),
                             start_new_session=True) as child:
        try:
            out, err = child.communicate(timeout=deadline)
        except subprocess.TimeoutExpired:
            stop(child)
            return None, 'timed out after %ds' % deadline
        except BaseException:
            # In a session of its own pytest does not hear the terminal's Ctrl-C, so an
            # interrupted matrix would leave it running under the mutant.
            stop(child)
            raise
    tail = out.strip().splitlines()
    return child.returncode, (tail[-1] if tail else err[-160:])


def stop(child):
    """Kill the child's process group, or the child alone where the group is already gone,
    and wait a bounded time for its pipes: a detached descendant may hold them for good."""
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        child.kill()
    try:
        child.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def outcome(code, tail):
    """Whether a run FAILED a case, passed it, or merely stopped working.

    `exit != 0` cannot tell the two apart, and the difference is the whole measurement: a
    mutant that breaks the import makes every case error, which reads as "caught" while the
    case never ran. Measured on this file's own fixtures — replacing a `def` line with a
    module-scope raise recorded two mutants as caught, and neither case had executed.

    The summary line alone is not the verdict either: it is the last line a run printed, and a
    plugin in the repository under review can print `1 failed` after it. A failure is pytest's
    exit 1 with a summary saying so, a pass is exit 0 with no failure in it, and a run whose two
    disagree is refused like a crash.
    """
    failed = re.search(r'(\d+) failed', tail)
    errored = re.search(r'(\d+) error', tail)
    # An error anywhere means some case did not run, whatever else the line says. Reading
    # "1 failed, 3 errors" as a clean catch was measured: a case that errored in fixture setup
    # was recorded caught, and the three that never ran were invisible.
    if errored:
        return 'error'
    if failed:
        return 'failed' if code == 1 else 'error'
    # A run that never ended has no status, and says nothing about where it stopped: it may
    # hang importing the module, before any test body runs, so it is a crash and not a catch.
    return 'passed' if code == 0 else 'error'


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
    # The bytes, and decoded here rather than read as text, so what goes back outside the
    # anchor is what was there: read_text() turns CRLF into LF and decodes with the locale's
    # codec, and re-encoding that as UTF-8 rewrote lines the mutant never named and mangled a
    # source that was not UTF-8 — the case runs against the file, so the file must be the one
    # the author has apart from the anchor.
    original = path.read_bytes()
    text = original.decode('utf-8', 'surrogateescape')
    anchor, becomes = spelled(text, mutant)
    hits = text.count(anchor)
    if hits != 1:
        bail('Mutant for %r: its anchor occurs %d times in %s. Zero means the mutation never '
             'landed and the run proves nothing; more than one means nobody knows which line '
             'carried it. This is not a formality — a matrix that printed "69 passed" with no '
             'mutant applied is why the anchor is counted.' % (mutant.get('case'), hits, mutant['file']))
    path.write_bytes(text.replace(anchor, becomes, 1).encode('utf-8', 'surrogateescape'))
    return path, original


def spelled(text, mutant):
    """The anchor and its replacement in the line ending this file uses. A spec spells them
    with \n, which a CRLF line ending does not spell, so the anchor is converted to match and
    the replacement is converted whatever the anchor needed: a single-line anchor matches a
    CRLF file untouched, and a replacement spanning lines would then have carried LF into it.
    """
    ending = '\r\n' if '\r\n' in text else '\n'
    anchor = mutant['anchor'] if mutant['anchor'] in text else mutant['anchor'].replace('\n', ending)
    # Normalised before it is spelled: a spec that already writes \r\n would otherwise have
    # its own carriage return doubled.
    return anchor, mutant['becomes'].replace('\r\n', '\n').replace('\n', ending)


def one(root, mutant, files, clean=None):
    """Each node the case collects, shown to pass alone on the clean tree, then run alone under
    the mutant, then restore whatever happens.

    The clean baseline is a property of the case, not of the mutant, so `clean` carries it
    between mutants that share one. Without it every mutant pays its case's baseline again,
    and a matrix nobody can afford to run is a matrix nobody runs.
    """
    seen = clean if clean is not None else {}
    if mutant['case'] not in seen:
        seen[mutant['case']] = baseline(root, files, mutant['case'])
    nodes_of_case = seen[mutant['case']]
    path, original = apply_mutant(root, mutant)
    try:
        # One pytest per node: run together under the selector, the summary line said some
        # test failed and not which, and a vacuous changed test was credited with what an
        # older test of the same name in another file caught.
        runs = [(node, *run_case(root, None, [node], deadline)) for node, deadline in nodes_of_case]
    finally:
        path.write_bytes(original)
    failed, saw = judged(mutant, runs)
    # The whole identity travels with the result, so a record's results can be told apart
    # the way the spec's mutants are: a result repeated to match a forged count is not two.
    # With it the nodes that failed, and their files: a file is credited when any node of it
    # failed, and the node says which — an older neighbour of the changed test is a file.
    return {'case': mutant['case'], 'file': mutant['file'], 'anchor': mutant['anchor'],
            'becomes': mutant['becomes'], 'caught': bool(failed), 'saw': saw,
            'nodes': sorted(failed),
            'tests': sorted({Path(node.split('::')[0]).as_posix() for node in failed})}


def baseline(root, files, case):
    """The nodes of the case shown to pass alone on the clean tree, as each then runs under a
    mutant, with the deadline those runs get. Shown passing together, a node that leaned on an
    earlier one's side effect failed alone under a mutation of something else entirely, and that
    failure was recorded as a catch.
    """
    nodes = ids(root, files, case)
    if not nodes:
        bail('Case %r collects no test under %s. A case pytest cannot find measures nothing.'
             % (case, ' '.join(files)))
    ran = []
    for node in nodes:
        began = time.monotonic()
        clean_code, clean_tail = run_case(root, None, [node])
        taken = time.monotonic() - began
        if clean_code != 0:
            bail('Case %r does not pass on the clean tree (%s: %s). A mutant that fails a case '
                 'which already fails measures nothing.' % (case, node, clean_tail))
        # Passed, not merely exited zero: pytest exits zero on a skip, and a mutant that changed
        # the skip condition made the node run and fail, which read as a catch. A skipped node
        # is left out of the measurement, the way ran_alone() leaves it out of the demand.
        if outcome(clean_code, clean_tail) == 'passed' and re.search(r'\d+ passed', clean_tail):
            ran.append((node, max(FLOOR, int(SLACK * taken) + 1)))
    if not ran:
        bail('Case %r runs no test on the clean tree under %s: every node it collects is skipped '
             'there, and a case that never runs measures nothing.' % (case, ' '.join(files)))
    return ran


def ran_alone(root, nodes):
    """Of these nodes, the ones that PASSED alone in this tree. A failure, an error and a skip
    are each excluded, since a test that did not run cannot be among those that failed and
    asking it to would be a demand nobody could satisfy.

    Asked of the nodes themselves rather than taken from what the matrix ran: the matrix runs
    what its cases select, and a test the author's selector passes over would have left the
    demand with nothing to ask about — which is the correction writing its own exemption.
    """
    kept = []
    for node in nodes:
        code, tail = run_case(root, None, [node])
        # Clean, not merely passing: a test whose body passes and whose teardown raises reads
        # `1 passed, 1 error`, and a mutant run that errors stops the matrix in judged(), never
        # counted as a catch — so demanding that node would be a demand nobody could satisfy.
        if outcome(code, tail) == 'passed' and re.search(r'\d+ passed', tail):
            kept.append(node)
    return kept


def judged(mutant, runs):
    """The nodes whose own run FAILED, and the line that said so. A run that errored is a
    crash and not a measurement, whatever the other nodes did."""
    errored = [tail for node, code, tail in runs if outcome(code, tail) == 'error']
    if errored:
        bail('Mutant for %r stopped the tree from loading or finishing rather than failing the '
             'case, or ended a run whose exit status and summary disagree (%s). That is a crash, '
             'not a measurement: the case may never have run, and every case would report the '
             'same. Mutate what the gate reads, not what the module needs to import or a loop '
             'needs to end.' % (mutant['case'], errored[0]))
    failed = [node for node, code, tail in runs if outcome(code, tail) == 'failed']
    said = {node: tail for node, code, tail in runs}
    saw = said[failed[0]] if failed else (runs[-1][2] if runs else 'no node collected for the case')
    return failed, saw


def shaped(rule):
    """A rule and its mutants in the shape the runtime reads: strings where it will compare
    or print them. Checked once, up front, because every field here is spec text an author
    wrote, and a list where a string was expected surfaced later as a crash in the runtime
    that read the record rather than as a refusal naming the rule."""
    # Containers before fields: a rule that is not a mapping, or a mutant that is not, has
    # no fields to read, and reading them anyway crashed where a refusal should have named it.
    if not isinstance(rule, dict):
        bail('A rule is a mapping with a name, an enumeration and mutants; %r is not a mapping.' % (rule,))
    if not isinstance(rule.get('rule'), str) or not rule['rule'].strip():
        bail('A rule must be named by a non-empty string; got %r.' % (rule.get('rule'),))
    if not isinstance(rule.get('enumeration'), str):
        bail('Rule %r declares its enumeration as %r, not a string.' % (rule['rule'], rule.get('enumeration')))
    if not isinstance(rule.get('mutants'), list):
        bail('Rule %r declares its mutants as %r, not a list.' % (rule['rule'], rule.get('mutants')))
    for mutant in rule['mutants']:
        if not isinstance(mutant, dict):
            bail('Rule %r has a mutant that is %r, not a mapping.' % (rule['rule'], mutant))
        for field in ('file', 'anchor', 'becomes', 'case'):
            if not isinstance(mutant.get(field), str) or not mutant[field]:
                bail('Rule %r has a mutant whose %s is %r, not a non-empty string.'
                     % (rule['rule'], field, mutant.get(field)))
        # Compared as spelled() will write them: a CRLF file takes either spelling of a line
        # break, so an anchor and a replacement differing only there change nothing either.
        if mutant['anchor'].replace('\r\n', '\n') == mutant['becomes'].replace('\r\n', '\n'):
            bail('Rule %r has a mutant of %s whose replacement is its anchor. It changes nothing, '
                 'so a case failing for any other reason would read the unchanged source as caught.'
                 % (rule['rule'], mutant['file']))


def place(root, name):
    """Where a file is, as far as the disk knows: its device and inode. A spelling is not a
    place — `./path`, `sub/../path`, an absolute path, a hard link and, on a filesystem that
    folds case, PATH — and the resolved path still told the last two apart. A file that is
    not there has no place and is named by its resolved path instead, so the refusal that
    names it fires later with the spelling the spec used."""
    path = Path(root) / name
    try:
        stat = path.stat()
    except OSError:
        return path.resolve()
    return (stat.st_dev, stat.st_ino)


def sites(root, mutants):
    """How many places in the source these mutants land on: each anchor resolved to its span
    in its file, spans that overlap merged, because an anchor is text and two different
    texts can name one place. An anchor that does not occur once is left to apply_mutant,
    which refuses it with the count."""
    spans, landed = {}, 0
    for mutant in mutants:
        # Read as apply_mutant reads it, bytes decoded with surrogateescape: read as text,
        # a source that is not UTF-8 raised here, before the decoding that was put in to
        # survive one — the count runs before apply_mutant, so the crash was all anyone saw.
        # A file that cannot be read counts as its own site, like an anchor that does not
        # occur once, so apply_mutant's refusal is the one that fires.
        try:
            text = (Path(root) / mutant['file']).read_bytes().decode('utf-8', 'surrogateescape')
        except OSError:
            landed += 1
            continue
        anchor = spelled(text, mutant)[0]
        at = text.find(anchor)
        if at >= 0 and text.count(anchor) == 1:
            spans.setdefault(place(root, mutant['file']), []).append((at, at + len(anchor)))
        else:
            landed += 1
    for runs in spans.values():
        end = -1
        for start, stop in sorted(runs):
            landed += start >= end
            end = max(end, stop)
    return landed


def matrix(root, spec, files):
    """Every rule, every mutant, with a survivor stopping the run."""
    results, clean = [], {}
    for rule in spec:
        shaped(rule)
    names = [r['rule'] for r in spec]
    if len(set(map(str, names))) != len(names):
        bail('Two rules share a name: a result is told from another by its rule, so each rule '
             'needs one of its own.')
    untested(root, spec, files)
    confined(root, spec)
    for rule in spec:
        declared = enumerated(root, rule)
        mutants = rule.get('mutants') or []
        if not mutants:
            bail('Rule %r declares no mutants.' % rule.get('rule'))
        seen = set()
        for mutant in mutants:
            # The file by its place, as the site count keys it: a spelling is not a place.
            key = (place(root, mutant['file']), mutant['anchor'], mutant['becomes'], mutant['case'])
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
        # The enumeration counts sites, and so does this: a site is where in the source the
        # mutation lands, so a second case, a second replacement, or a second anchor over
        # the same span is a second measurement of it, not the site the command counted next.
        landed = sites(root, mutants)
        if declared is not None and declared > landed:
            bail('Rule %r enumerates %d case(s) by its own command and mutates %d site(s). The '
                 'list is short by %d: a case nothing mutates is a case nothing covers.'
                 % (rule.get('rule'), declared, landed, declared - landed))
        for mutant in mutants:
            result = one(root, mutant, files, clean)
            result['rule'] = rule.get('rule')
            results.append(result)
            print('%-8s %-46s %s' % ('caught' if result['caught'] else 'SURVIVED',
                                     mutant['case'], result['saw']))
    return results


def untested(root, spec, files):
    """Refuse a mutant of a file the matrix runs as a test, or of code only tests stand on.
    Breaking a test makes it fail whatever the code it covers does, so `assert 1 == 1` mutated
    to `1 == 2` is caught, and a vacuous test would carry a correction's evidence; a helper the
    test imports does the same from one file over. So a conftest.py is refused, and any file
    under a directory TEST_DIRECTORIES names. The directory's name and not its contents: a test
    kept beside the module it covers shares that module's directory, and refusing the
    directory of every collected test refused the code under review. A helper named neither
    way is a stated gap. The directory is read where the file is, relative to the root: a
    spelling through `..`, an absolute one or a symlink names the same place."""
    tests = {place(root, name) for name in nodes(root, files)}
    real = os.path.realpath(root)
    for rule in spec:
        for mutant in rule['mutants']:
            where = os.path.relpath(os.path.realpath(os.path.join(root, mutant['file'])), real)
            parts = [part.lower() for part in Path(where).parts[:-1]]
            if place(root, mutant['file']) in tests or Path(where).name == 'conftest.py' \
                    or TEST_DIRECTORIES.intersection(parts):
                bail('Mutant for %r mutates %s, which the matrix runs as a test or which tests '
                     'stand on. A catch there measures the test and not the rule: mutate the '
                     'code the test covers.' % (mutant['case'], mutant['file']))


def confined(root, spec):
    """Refuse a mutant of a file outside the reviewed tree, or one git does not track there.
    A matrix is evidence about the candidate: a catch earned by mutating a helper in /tmp, or an
    untracked file no diff shows, measures something no review reads, and the fingerprint would
    hash it as if it were the tree. The file is read where it is, as untested() reads it; a file
    that is not there is left to apply_mutant, whose refusal names it."""
    real = os.path.realpath(root)
    for rule in spec:
        for mutant in rule['mutants']:
            resolved = os.path.realpath(os.path.join(root, mutant['file']))
            if not os.path.isfile(resolved):
                continue
            where = os.path.relpath(resolved, real)
            outside = where == os.pardir or where.startswith(os.pardir + os.sep)
            if outside or subprocess.run(['git', '-C', real, 'ls-files', '--error-unmatch', '--', where],
                                         capture_output=True).returncode != 0:
                bail('Mutant for %r mutates %s, which is %s. A matrix measures the tree under '
                     'review: mutate a file the candidate tracks.'
                     % (mutant['case'], mutant['file'],
                        'outside the reviewed tree' if outside else 'not tracked in it'))


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


def arguments(root, files):
    """The test paths as pytest gets them, for the run and for the collect alike: the file
    part spelled relative to the root, a node id's selector kept. Both take these, so what
    the collect names is what the run selected from — a node id stripped of its selector
    widened the collect to the whole file while the run stayed on the node."""
    real = os.path.realpath(root)
    out = []
    for f in files:
        path, _, node = str(f).partition('::')
        rel = os.path.relpath(os.path.realpath(os.path.join(root, path)), real)
        out.append(rel + ('::' + node if node else ''))
    return out


def collected(root, files, results):
    """Per test file pytest collects under these paths, spelled as pytest spells it, the spec's
    cases a test there failed under a mutant. The files are asked of pytest rather than read
    from the text: a case named in a comment, a string or a class pytest skips is not a case
    that ran, and a directory holds whatever python_files says it holds — test_*.py, *_test.py,
    or a project's own rule — none of which a substring search could know. The cases come from
    the results, each naming the files whose node failed alone under its mutant: collected is
    not run, and run is not failed — a file whose selected tests passed under every mutant
    discriminated nothing, whatever it defines."""
    out = {name: set() for name in nodes(root, files)}
    for result in results:
        for name in result['tests']:
            out.setdefault(name, set()).add(result['case'])
    return {name: sorted(cases) for name, cases in out.items()}


def nodes(root, files, selector=None, tolerant=False):
    """The files of the node ids pytest collects under these paths, and under a selector when
    one is given, each spelled as pytest spells it."""
    return sorted({Path(node.split('::')[0]).as_posix()
                   for node in ids(root, files, selector, tolerant)})


def ids(root, files, selector=None, tolerant=False):
    """The node ids pytest collects under these paths, and under a selector when one is given.
    A collect that fails for any reason but finding nothing is refused, since a record built
    from a broken collect would name nothing and prove the same.

    The ids come from pytest's own collection, written by a plugin to a file this runtime names,
    so nothing a module prints can be one. Read from stdout, an id was any line holding `::`, and
    a module that printed while it failed to import could name any file it liked — after the
    report banner, or, from a conftest below the collected directory, ahead of every real id.

    Tolerantly, a run that failed still answers with whatever it collected before failing, so a
    directory one broken file would otherwise silence still answers; a run that collected
    nothing answers nothing, whatever it exited with.
    """
    # The rootdir by its real path: handed a root reached through a symlink, pytest spelled
    # every id against the argument's own directory instead — a bare name for a file under
    # tests/ — and the cwd is spelled the same so the two agree.
    real = os.path.realpath(root)
    token = secrets.token_hex(8)
    with tempfile.TemporaryDirectory() as box:
        done, where = collect_run(real, root, files, selector, token, box)
        if not tolerant and done.returncode not in (0, 5):
            bail('pytest could not collect %s (exit %d): %s' % (' '.join(files), done.returncode,
                 ((done.stdout + done.stderr).strip().splitlines() or ['no output'])[-1]))
        vouched = reported(where, token)
        # A collect that pytest completed and the plugin did not report is not an empty
        # directory: the plugin did not run. Answering [] there would say "no test here".
        if vouched is None and done.returncode in (0, 5):
            bail('pytest collected %s and its collector never reported what it found, so nothing '
                 'here can say what was collected. Something in the repository under review kept '
                 'it from reporting.' % ' '.join(files))
        return sorted(vouched or [])


def collect_run(real, root, files, selector, token, box):
    """Run pytest's collect with the collector loaded under a name made for this run.

    Loaded by a name anyone could know, the collector was replaced: pytest resolves a -p name
    through places the repository controls before the directory this runtime adds, and a
    project's module found there took its place and left its channel in the environment for a
    conftest to write an empty report with. Predicting that path lost to the next entry into it. A name carrying this run's token,
    in a directory of this run's own, is one nothing in the repository can place or declare.
    """
    name = 'bymax_collect_' + token
    shutil.copyfile(Path(__file__).with_name('review_collect.py'), Path(box, name + '.py'))
    env = pytest_env()
    env['PYTHONPATH'] = os.pathsep.join([box, env['PYTHONPATH']]) if env.get('PYTHONPATH') else box
    env['BYMAX_COLLECT_TOKEN'] = token
    env['BYMAX_COLLECT_OUT'] = str(Path(box, 'collected'))
    args = [*PYTEST, '--collect-only', '--rootdir', real, '-p', name,
            *arguments(root, files)] + (['-k', selector] if selector else [])
    # A collect runs the repository's import-time code, and a loop there never returns: bounded
    # like a mutant run, its group killed if the wait times out or raises.
    with subprocess.Popen(args, cwd=real, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, env=env, start_new_session=True) as child:
        try:
            out, err = child.communicate(timeout=CLEAN)
        except subprocess.TimeoutExpired:
            stop(child)
            bail('pytest did not finish collecting %s in %ds. A collect that never ends names no '
                 'test, and the matrix cannot run what it cannot list.' % (' '.join(files), CLEAN))
        except BaseException:
            stop(child)
            raise
    return subprocess.CompletedProcess(args, child.returncode, out, err), Path(env['BYMAX_COLLECT_OUT'])


def reported(where, token):
    """The node ids a collect vouched for with this run's token, or None where it said nothing.

    None and an empty list are different answers: nothing at all means the plugin never ran,
    while an empty list means it ran and collected no test. Lines without the token are not
    read, so a file left by an earlier run and a project writing to the same path say nothing.
    """
    try:
        lines = where.read_text().splitlines()
    except OSError:
        return None
    if ('%s %s' % (MARK, token)) not in lines:
        return None
    return [line.partition(' ')[2] for line in lines
            if line.startswith(token + ' ') and line.partition(' ')[2]]


def record(root, spec_path, files, out=None):
    """Run the matrix and write what happened; a survivor is a failure, not a note."""
    spec = json.loads(Path(spec_path).read_text())
    if not isinstance(spec, list) or not spec:
        bail('A matrix is a non-empty list of rules.')
    results = matrix(root, spec, files)
    survivors = [r for r in results if not r['caught']]
    head, names, tree = fingerprint(root, spec)
    # The test files pytest collected travel with the record, each with the cases a test of
    # it failed under a mutant: each result names the files whose node failed, so the mapping is what
    # the results add up to, and a reader can check it against them file by file.
    payload = {'head': head, 'tree': tree, 'files': names, 'rules': len(spec),
               'mutants': len(results), 'survivors': [r['case'] for r in survivors],
               'tests': collected(root, files, results),
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
    """The command line: a spec, the test paths to run it over, and optionally where to
    write the record. Exit 0 with every mutant caught, 2 for any refusal — a survivor,
    an anchor that does not occur once, a spec out of shape — so a caller keying on 2
    reads BLOCKED and nothing else."""
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
