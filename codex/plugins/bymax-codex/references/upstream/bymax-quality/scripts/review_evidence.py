"""Evidence layer: which tests a candidate's delta changed and who wrote them, and the measured
mutation matrix a correction that changes a test must carry, bound to the candidate it
measured and never to what an author said about it."""
import contextlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from review_git import clean_head, git, git_raw, require


TEST_PATH = re.compile(r'(^|/)(tests?|spec|__tests__)/|(^|/)test_[^/]+\.py$|_test\.|\.test\.|\.spec\.', re.IGNORECASE)
TEST_DIRECTORY = re.compile(r'(^|/)(tests?|spec|__tests__)/', re.IGNORECASE)
PROSE_SUFFIXES = ('.md', '.markdown', '.adoc')
# Plain text and data formats are test material only inside a test directory:
# tests/golden/expected.txt and tests/fixtures/data.json count, openapi/v1.spec.yaml does not.
INSIDE_ONLY_SUFFIXES = ('.txt', '.rst', '.yaml', '.yml', '.json', '.toml')


def is_test_path(path):
    """A test by location or name; prose never, text and data only inside a test directory.

    What a correction may not be asked for is a CASE in a file pytest collects none from,
    which is the demand's business and not this predicate's.
    """
    lower = path.lower()
    if not TEST_PATH.search(path) or lower.endswith(PROSE_SUFFIXES):
        return False
    return bool(TEST_DIRECTORY.search(path)) or not lower.endswith(INSIDE_ONLY_SUFFIXES)


def tests_changed(base, head):
    """What a delta did to tests, read from the diff, which is the only place it can be read.

    Added or modified only: deleting the test that caught a defect is not a regression.
    Renames are not detected, so a renamed test is listed under its new path as added instead
    of vanishing from the list both reviewers see. Deleted tests never count as evidence, but
    reviewers must see them to judge the deletion, so they come back separately.

    What a merge carried in is not what this delta wrote. Merging the base branch is the only
    way to resolve a conflict on a branch that may not be rebased, and it puts every test the
    other side ever wrote into this diff — which asked the matrix for a case inside suites the
    correction never touched, a demand nobody can satisfy.
    """
    # NUL-separated, because git quotes a path it prints one to a line: tests/test_café.py came
    # back as "tests/test_caf\303\251.py", matched no file, and the change read as testless.
    changed = [p for p in git_raw('diff', '-z', '--name-only', '--no-renames', '--diff-filter=AM',
                                  base, head).split('\0') if p]
    removed = [p for p in git_raw('diff', '-z', '--name-only', '--no-renames', '--diff-filter=D',
                                  base, head).split('\0') if p]
    mine = written_here(base, head)
    ours = [name for name in changed if name in mine]
    elsewhere = collected_elsewhere([name for name in ours if not is_test_path(name)])
    return ([name for name in ours if is_test_path(name) or name in elsewhere],
            [name for name in removed if is_test_path(name)])


def collected_elsewhere(paths):
    """The Python files among these that pytest collects a test from where they sit, though no
    spelling TEST_PATH knows names them: a repository that sets `python_files = check_*.py`
    tells pytest, and only pytest reads it. Each directory is asked once, strictly; a collect
    that failed still answers for the files it collected, and a changed file it did not collect
    refuses by name. Read as "no test here", a conftest that stopped the collect or a test that
    failed to import made a test the project names its own way into code, and asked no matrix.
    """
    import review_matrix
    root = git('rev-parse', '--show-toplevel')
    wanted = {path for path in paths if path.endswith('.py') and Path(root, path).is_file()}
    found, unanswered = set(), []
    for where in sorted({str(Path(path).parent) for path in wanted}):
        try:
            found.update(review_matrix.nodes(root, [where]))
            continue
        except review_matrix.Unfinished:
            unanswered.append(where)
            continue
        except SystemExit:
            pass
        with contextlib.suppress(SystemExit, review_matrix.Unfinished):
            found.update(review_matrix.nodes(root, [where], tolerant=True))
        if any(str(Path(path).parent) == where and path not in found for path in wanted):
            unanswered.append(where)
    require(not unanswered, 'pytest could not say whether the Python files this delta changed in '
            '%s hold a test, so nothing here can say whether it changed one. Fix the collect '
            'there, then run this again.' % ', '.join(unanswered))
    return wanted & found


def merged_in_tests(base, head):
    """The test files this delta changed that no commit of its own first-parent line wrote.

    A merge of the base branch and a merge of a branch of one's own put work here the same way,
    so this names it rather than guessing — and it says no more than that, because a base that
    is not an ancestor of head puts files here that no merge touched at all.
    """
    changed = [p for p in git_raw('diff', '-z', '--name-only', '--no-renames', '--diff-filter=AM',
                                  base, head).split('\0') if p]
    mine = written_here(base, head)
    return [name for name in changed if is_test_path(name) and name not in mine]


def written_here(base, head):
    """Every path a commit of this delta's own line wrote.

    Provenance, and read from the first-parent line, because nothing in the graph distinguishes
    the two merges that matter: merging the base branch in and merging a branch of one's own
    have the same shape. Telling them apart by content dropped a test this delta wrote that the
    other side wrote identically; by descent, it kept what the base branch added after the
    merge-base; by naming a ref, it kept what a sibling branch's own base wrote and dropped what
    a branch already merged upstream had written. Each was wrong in both directions, so the
    question stops being asked of the shape.

    A merge on that line is read by its combined diff, which names only what differs from every
    parent: the resolution somebody typed, and never the files the other side carried over.

    The limit, stated because it is one: work merged in with `--no-ff` from a side branch sits
    off the first-parent line, so only the resolution counts as written here.
    """
    written = set()
    for row in git('rev-list', '--first-parent', '--parents', '%s..%s' % (base, head)).splitlines():
        shape = ['-c'] if len(row.split()) > 2 else ['--root']
        written.update(p for p in git_raw('diff-tree', '-r', '-z', '--no-commit-id', '--name-only',
                                          '--no-renames', *shape, row.split()[0]).split('\0') if p)
    return written


def matrix_run(args, directory, state):
    """Run the declared matrix through the runtime and keep what happened, not what was said.

    An author's `observed: the mutant fails the case` is a sentence. This is the measurement,
    taken here so the record is the runtime's and is bound to the candidate it was taken on.
    """
    import review_matrix
    # Recorded under the HEAD it measured, not under the campaign's current candidate: this
    # runs between committing a correction and opening the round that reviews it, so the
    # state in hand still describes the round before.
    head = clean_head()
    where = directory / ('matrix-' + head + '.json')
    # Gone before the attempt, not replaced after it: a run refused before it writes, by an
    # anchor, a spec or a collect, would otherwise leave an earlier run's record for start to
    # accept as the measurement of a spec it never ran.
    where.unlink(missing_ok=True)
    return review_matrix.record(git('rev-parse', '--show-toplevel'), args.spec,
                                list(args.paths), out=str(where))


def matrix_first(state, directory):
    """A correction that changes a test must carry a measured matrix, not a claim of one.

    Only the runtime can establish that a mutant applied, that its case passed clean first,
    and that it then failed — which is why `--probe` alone never could.
    """
    if state['round'] == 1 or not state.get('regression_tests'):
        return
    # Scoped to a correction that changes a TEST, because that is what the matrix proves: a
    # gate discriminates. Every vacuous gate measured on this loop lived in a test file and
    # passed its own suite. A correction that changes no test has no gate to mutate, and
    # demanding one there would buy a slower suite and no evidence.
    #
    # And scoped to a test the matrix can run at all. It runs pytest, while a test path here
    # is any repository's, so on a project whose suite is Jest or Cargo the record demanded
    # could never be produced and the correction was blocked for good. Asked of pytest: what
    # it collects no test from is not a gate this runtime can mutate.
    answered = [(path, collects_a_test(path)) for path in state['regression_tests']]
    # An unanswerable collect is not an answer: read as "no test here" it emptied the list and
    # returned, skipping the whole gate without a word.
    unanswered = [path for path, said in answered if said is None]
    require(not unanswered, 'pytest could not say whether %s holds a test, so nothing here can '
            'say whether this correction needs a matrix. Fix the collect, then run '
            '`review_flow.py matrix`.' % ', '.join(unanswered))
    runnable = [path for path, said in answered if said]
    if not runnable:
        return
    where = directory / ('matrix-' + state['head'] + '.json')
    require(where.exists(),
            'This correction changes %s and no measured mutation matrix exists for %s. Run '
            '`review_flow.py matrix --spec <file> <test paths>` first: a mutant that survives is '
            'the finding, and a matrix reported rather than run is the one step of this protocol '
            'that has only ever been the author\'s word.'
            % (', '.join(runnable), state['head'][:12]))
    kept, names = matrix_bound_to_this_tree(json.loads(where.read_text()), state['head'])
    ran_the_changed_tests(kept, runnable)
    # Before caught_with_the_changed_test, never after: the nodes it reads are the results,
    # and a record whose results are not a list crashed there rather than refused by name.
    results_agree(kept, names)
    import review_matrix
    added = tests_added(state['review_base'], runnable)
    caught_with_the_changed_test(kept, review_matrix.ran_alone(git('rev-parse', '--show-toplevel'), added))


def matrix_bound_to_this_tree(kept, head):
    """The record, once it is shown to be about this candidate and this tree. Returns it
    with the names of the files it mutated.
    """
    require(kept.get('head') == head, 'The recorded matrix names head %s, not this '
            'candidate. A record bound to another head measured another tree.'
            % str(kept.get('head'))[:12])
    require(kept.get('mutants'), 'The recorded matrix measured no mutants. A matrix that mutates '
            'nothing answers nothing.')
    require(kept.get('tree'), 'The recorded matrix carries no fingerprint of the files it '
            'mutated, so nothing ties it to what is here now.')
    require(not kept.get('survivors'), 'The recorded matrix has survivors: '
            + ', '.join(str(s) for s in kept['survivors']) + '. A gate nothing can break is decoration.')
    # Recomputed, not trusted. The field was tested for presence and never for agreement, so
    # a record saying `tree: x` bound itself to nothing while two sentences said it did — the
    # head alone held the binding, and only on the path that refuses a dirty worktree.
    import review_matrix
    names = kept.get('files')
    require(names is not None, 'The recorded matrix does not name the files it mutated, so its '
            'fingerprint cannot be checked against this tree. Re-run `review_flow.py matrix`.')
    require(isinstance(names, list) and all(isinstance(n, str) for n in names), 'The recorded '
            'matrix names its files as %r, not a list of paths. Re-run `review_flow.py matrix`.' % (names,))
    now = review_matrix.digest(git('rev-parse', '--show-toplevel'), names)
    require(now == kept['tree'], 'The recorded matrix was measured on other contents of %s: its '
            'fingerprint does not match what is here now. A record is bound to the tree it '
            'measured; re-run the matrix on this one.' % ', '.join(names))
    return kept, names


def ran_the_changed_tests(kept, changed):
    """The record names the test files pytest collected, each with the cases a test of it
    failed under a mutant, and the tests this correction changed must be among them with a
    case each: a matrix over some other file measured nothing about the new gate, and a
    changed test that failed under no mutant discriminates nothing.

    Only the changed files pytest collects a test from reach this rule, which its caller
    decides: a file it collects none from is still a test path a correction may change, and
    no matrix could ever name a case that ran in one, so demanding it was a refusal nobody
    could satisfy.
    """
    ran = kept.get('tests')
    require(isinstance(ran, dict) and all(isinstance(p, str) and isinstance(c, list)
                                          and all(isinstance(x, str) for x in c) for p, c in ran.items()),
            'The recorded matrix does not name the tests it ran. Re-run `review_flow.py matrix`.')
    missing = sorted(set(changed) - set(ran))
    require(not missing, 'The recorded matrix did not run %s, which this correction changes; a '
            'matrix over other tests measured nothing about the gate that changed. Re-run '
            '`review_flow.py matrix` over it.' % ', '.join(missing))
    # Named is not caught: a file the record names whose selected tests passed under every
    # mutant, or were all deselected, measured nothing about the gate in it — a vacuous test
    # beside an older one of the same name was credited with the older one's catch while the
    # run read one summary line for both.
    idle = sorted(p for p in changed if not ran[p])
    require(not idle, 'The recorded matrix caught nothing in %s, which this correction changes: '
            'the file was named, and no test of it failed under any mutant. Add a mutant its '
            'own case catches and re-run `review_flow.py matrix`.' % ', '.join(idle))


def collects_a_test(path):
    """Whether pytest collects a test from this file when it collects the directory it sits
    in. Named directly, pytest collects a file whatever it is called, so asking about the
    file alone would call every helper a test.

    A file it collects nothing from can carry no case, and a file gone from the tree carries
    none either. A collect that cannot answer at all is None and never False: read as "no test
    here" it let the caller skip the gate in silence.

    A neighbour with a broken import is enough to stop the directory answering, and refusing the
    round for a file that is not implicated is the blocked-for-good shape this gate exists to
    remove. So the directory is asked a second time tolerantly, which is the same question with
    the neighbour's failure no longer fatal. The file alone is asked only to tell "not a test
    module" from "this file is what failed".
    """
    import review_matrix
    root = git('rev-parse', '--show-toplevel')
    if not path.endswith('.py') or not Path(root, path).is_file():
        return False
    where = [str(Path(path).parent) or '.']
    # A collect that ran out of time answered nothing, and the file alone collecting fine would
    # then read as "not a test module": the gate opened on a neighbour that loops on import.
    try:
        return path in review_matrix.nodes(root, where)
    except review_matrix.Unfinished:
        return None
    except SystemExit:
        pass
    try:
        if path in review_matrix.nodes(root, where, tolerant=True):
            return True
    except review_matrix.Unfinished:
        return None
    except SystemExit:
        pass
    try:
        review_matrix.ids(root, [path])
    except SystemExit:
        return None
    return False


def tests_added(base, names):
    """The node ids this correction added, asked of pytest on both sides: what it names in
    these files here, and does not name in them at the base.

    Read from the source instead, this meant predicting what pytest collects and how Python
    binds a name, and every round of that found another shape it had got wrong. The two
    collects are facts, and the question is the one the record answers.
    A base that cannot be collected answers nothing, which demands nothing.
    """
    import review_matrix
    root = git('rev-parse', '--show-toplevel')
    here = [name for name in names if Path(root, name).is_file()]
    now = set(review_matrix.ids(root, here)) if here else set()
    with archived(base) as older:
        kept = [name for name in names if Path(older, name).is_file()]
        try:
            before = set(review_matrix.ids(older, kept)) if kept else set()
        except SystemExit:
            return []
    return sorted(now - before)


@contextlib.contextmanager
def archived(revision):
    """That revision's tree, unpacked outside the repository. Out of the object store rather
    than through a worktree, so nothing is added to this repository's bookkeeping and no
    checkout of it is touched."""
    where = tempfile.mkdtemp()
    try:
        packed = Path(where, 'tree.tar')
        with packed.open('wb') as handle:
            subprocess.run(['git', 'archive', revision], stdout=handle, check=True,
                           cwd=git('rev-parse', '--show-toplevel'))
        subprocess.run(['tar', '-xf', str(packed), '-C', where], check=True)
        packed.unlink()
        yield where
    finally:
        shutil.rmtree(where, ignore_errors=True)


def caught_with_the_changed_test(kept, wanted):
    """Every test this correction added must be a test that caught something.

    Every, not one of them: a file is credited when any node of it failed, which an older
    neighbour of the new test satisfies, and one added test that catches would carry the
    vacuous one beside it.
    """
    # Whole ids: an added parameter of an older test is a node of its own, and without its
    # parameters it was credited by the parameter beside it.
    failed = {node for r in kept.get('results') or [] for node in (r.get('nodes') or [])}
    idle = [node for node in wanted if node not in failed]
    require(not idle, 'The recorded matrix caught nothing with %s, which this correction adds: '
            '%s failed under a mutant and %s did not. A test that already discriminated proves '
            'nothing about the one added beside it.'
            % (', '.join(idle), ', '.join(sorted(failed)) or 'nothing', ', '.join(idle)))


def results_agree(kept, names):
    """The record's summary fields are its own and mutable; the results are what was measured,
    so each summary is checked against them. A survivor list cleared by hand passed here while
    a result still said caught: false."""
    results = kept.get('results')
    # Shape first, fields second: every field below is JSON an author can edit, and a
    # value of the wrong type surfaced as a crash inside a comparison rather than as this
    # refusal. The containers come first of all: a count that is not a number or results
    # that are not a list have nothing inside them to compare.
    # A boolean is an int to isinstance, and JSON true is not a count the matrix writes.
    odd = [f for f, kind in (('results', list), ('mutants', int))
           if not isinstance(kept.get(f), kind) or isinstance(kept.get(f), bool)]
    require(not odd, 'The recorded matrix is in a shape the runtime never writes (%s). Re-run '
            '`review_flow.py matrix`.' % ', '.join(odd))
    for result in results:
        odd = [f for f in ('rule', 'file', 'anchor', 'becomes', 'case')
               if not isinstance(result.get(f), str)] if isinstance(result, dict) else ['result']
        if isinstance(result, dict) and not isinstance(result.get('caught'), bool):
            odd.append('caught')
        for field in ('tests', 'nodes'):
            if isinstance(result, dict) and not (isinstance(result.get(field), list)
                                                 and all(isinstance(x, str) for x in result[field])):
                odd.append(field)
        require(not odd, 'The recorded matrix has a result in a shape the runtime never writes '
                '(%s). Re-run `review_flow.py matrix`.' % ', '.join(odd))
    mutated = {r.get('file') for r in results}
    require(set(names) == mutated, 'The recorded matrix names %s but its results mutated %s. '
            'Re-run `review_flow.py matrix`.' % (', '.join(names), ', '.join(sorted(mutated)) or 'nothing'))
    require(len(results) == kept.get('mutants'), 'The recorded matrix counts %s mutants and carries '
            '%d results; a summary its results do not add up to measured nothing. Re-run '
            '`review_flow.py matrix`.' % (kept.get('mutants'), len(results)))
    # The rule is part of it: the matrix dedupes per rule and records a mutation shared by
    # two rules twice, and an identity without the rule refused the runtime's own record.
    identities = [(r.get('rule'), r.get('file'), r.get('anchor'), r.get('becomes'), r.get('case'))
                  for r in results]
    require(len(set(identities)) == len(identities), 'The recorded matrix repeats a result: two '
            'results with one identity are one measurement, so the count they add up to is not '
            'the count of mutants. Re-run `review_flow.py matrix`.')
    # `is not True`, not falsiness: the record is JSON an author can edit, and the string
    # "false" is truthy, so a surviving result retyped that way read as caught.
    uncaught = [r.get('case') for r in results if r.get('caught') is not True]
    require(not uncaught, 'The recorded matrix has results it did not catch: %s. Its survivor '
            'list said otherwise; the results are what was measured.'
            % ', '.join(uncaught))
    mapping_agrees(kept, results)


def mapping_agrees(kept, results):
    """The tests mapping, file by file: what a file is said to hold must be what the results
    say was caught there, or the mapping is a summary saying so — a measured case moved
    to another file's entry was accepted while the check read cases alone."""
    # Both directions: a file a result names must be in the mapping, or the record's results
    # say the case ran somewhere the mapping never mentions.
    mapping = kept.get('tests') if isinstance(kept.get('tests'), dict) else {}
    stray = sorted({f for r in results for f in r.get('tests', [])} - set(mapping))
    require(not stray, 'The recorded matrix has results caught in %s, which its tests mapping '
            'never names. Re-run `review_flow.py matrix`.' % ', '.join(stray))
    for name, cases in mapping.items():
        held = {r.get('case') for r in results if name in r.get('tests', [])}
        wrong = sorted(set(cases) ^ held)
        require(not wrong, 'The recorded matrix says %s held %s, which its results do not: they '
                'measured %s there. Re-run `review_flow.py matrix`.'
                % (name, ', '.join(wrong), ', '.join(sorted(held)) or 'nothing'))
