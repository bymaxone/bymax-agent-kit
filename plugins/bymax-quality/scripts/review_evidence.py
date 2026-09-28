"""Evidence layer: which tests a candidate's delta changed and who wrote them, and the measured
mutation matrix a correction that changes a test must carry, bound to the candidate it
measured and never to what an author said about it."""
import contextlib
import importlib.util
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
# pytest's refusal of a file nothing collects, in 8 and later and in 7. Not "found no collectors
# for": that is written when every collector on the path failed, which answers nothing.
NO_COLLECTOR = r'no match in any of|no name .* in any of'


def is_test_path(path):
    """A test by location or name; prose never, text and data only inside a test directory.

    What a correction may not be asked for is a CASE in a file pytest collects none from,
    which is the demand's business and not this predicate's.
    """
    lower = path.lower()
    if not TEST_PATH.search(path) or lower.endswith(PROSE_SUFFIXES):
        return False
    return bool(TEST_DIRECTORY.search(path)) or not lower.endswith(INSIDE_ONLY_SUFFIXES)


def tests_changed(base, head, branch=''):
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
    mine = written_here(base, head, branch)
    ours = [name for name in changed if name in mine]
    elsewhere = collected_elsewhere([name for name in ours if not is_test_path(name)])
    return ([name for name in ours if is_test_path(name) or name in elsewhere],
            removed_tests(base, removed))


def removed_tests(base, removed):
    """The deleted files that were tests at the base: named like one, or collected there. A
    deleted file cannot be asked about where it is gone, so the base's tree is asked, and a
    directory it cannot answer for keeps its files: a deletion reviewers are not shown is the
    one they cannot judge. A file that failed to collect there, or sits under a directory
    that did, is kept too: the tolerant collect leaves it out of what it found."""
    import review_matrix
    named = [name for name in removed if is_test_path(name)]
    other = [name for name in removed if not is_test_path(name)]
    if not other or importlib.util.find_spec('pytest') is None:
        return named
    found = set()
    with archived(base) as older:
        wanted = [name for name in other if name.endswith('.py') or under_a_collect_hook(older, name)]
        for where in sorted({str(Path(name).parent) or '.' for name in wanted}):
            here = [name for name in wanted if (str(Path(name).parent) or '.') == where]
            try:
                collected, failed = review_matrix.walked(older, [where])
            except (SystemExit, review_matrix.Unfinished):
                found.update(here)
                continue
            found.update(collected)
            found.update(name for name in here
                         if {name, *(p.as_posix() for p in Path(name).parents)} & failed)
    return sorted(named + [name for name in other if name in found])


def collected_elsewhere(paths):
    """The files among these that pytest collects a test from where they sit, though no
    spelling TEST_PATH knows names them: a repository that sets `python_files = check_*.py`
    tells pytest, and only pytest reads it. A file of another format is asked only beneath a
    conftest naming a collection hook: asking about every
    changed document would collect the directory of each, the repository root included, on
    every prompt.

    Each directory is asked once. Where that collect fails, each file is asked as
    collects_a_test() asks it, and one it cannot rule out is kept: matrix_first() then refuses
    it by name, on the rounds that ask for a matrix and no others. Where it ran out of time,
    every file is kept unasked, since each ask would wait out the same deadline again. Refusing
    here blocked every round, round one included, for a module beside a broken test. With no
    pytest to ask, nothing here is a test pytest collects.
    """
    import review_matrix
    if importlib.util.find_spec('pytest') is None:
        return set()
    root = git('rev-parse', '--show-toplevel')
    wanted = {path for path in paths if Path(root, path).is_file()
              and (path.endswith('.py') or under_a_collect_hook(root, path))}
    found = set()
    for where in sorted({str(Path(path).parent) for path in wanted}):
        here = [path for path in wanted if str(Path(path).parent) == where]
        try:
            found.update(review_matrix.nodes(root, [where]))
        except review_matrix.Unfinished:
            found.update(here)
        except SystemExit:
            found.update(path for path in here if collects_a_test(path) is not False)
    return wanted & found


def under_a_collect_hook(root, path):
    """Whether a conftest.py from this file's directory up to the root names
    `pytest_collect_file`, which is how a conftest collects a file that is not Python."""
    for where in [Path(path).parent, *Path(path).parent.parents]:
        conftest = Path(root, where, 'conftest.py')
        if conftest.is_file() and 'pytest_collect_file' in conftest.read_text(errors='replace'):
            return True
    return False


def merged_in_tests(base, head, branch=''):
    """The test files this delta changed that no commit of its own first-parent line wrote.

    A merge of the base branch and a merge of a branch of one's own put work here the same way,
    so this names it rather than guessing — and it says no more than that, because a base that
    is not an ancestor of head puts files here that no merge touched at all.
    """
    changed = [p for p in git_raw('diff', '-z', '--name-only', '--no-renames', '--diff-filter=AM',
                                  base, head).split('\0') if p]
    mine = written_here(base, head, branch)
    theirs = [name for name in changed if name not in mine]
    elsewhere = collected_elsewhere([name for name in theirs if not is_test_path(name)])
    return [name for name in theirs if is_test_path(name) or name in elsewhere]


def written_here(base, head, branch=''):
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
    off the first-parent line, so only the resolution counts as written here — unless the round
    was told its base branch. Then a commit off that line is this delta's too when the base
    branch does not reach it: a side branch merged in. The line itself is never filtered by the
    branch, since a branch the base has already merged is still this delta's work.
    """
    written = set()
    rows = git('rev-list', '--first-parent', '--parents', '%s..%s' % (base, head)).splitlines()
    if branch:
        # Resolved to a commit first, and only the commit reaches rev-list: a ref name that
        # begins with a dash would otherwise be read as an option.
        tip = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', '--end-of-options',
                              branch + '^{commit}'], capture_output=True, text=True).stdout.strip()
        require(tip, 'The base branch %s names no commit here any more; start the round again with '
                '--base-branch naming the branch this work merges into.' % branch)
        line = {row.split()[0] for row in rows}
        rows += [row for row in git('rev-list', '--parents', '%s..%s' % (base, head), '--not', tip).splitlines()
                 if row.split()[0] not in line]
    for row in rows:
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
    # runs between committing a correction and opening the round that reviews it.
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
    asked = {}
    answered = [(path, collects_a_test(path, asked)) for path in state['regression_tests']]
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
    before, unread = failing_before(state['review_base'], state['regression_tests'], runnable)
    demanded = sorted(set(added) | set(before))
    caught_with_the_changed_test(kept, review_matrix.ran_alone(git('rev-parse', '--show-toplevel'), demanded))
    # The files whose nodes did run there, so the note can tell "every node passed" from "none ran".
    return {'failing_before': before, 'unread_before': unread,
            'read_before': [path for path in runnable if path not in unread]}


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
    # Non-empty, not merely present: digest([]) is the digest of nothing, and a record naming
    # no file with that digest would be bound to nothing. A matrix with a mutant always names
    # the file it mutated.
    require(names, 'The recorded matrix does not name the files it mutated, so its '
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


def collects_a_test(path, asked=None):
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

    `asked` keeps each directory's answers across calls, so a caller asking about several files
    of one directory collects it once: a directory that ran out of time otherwise waited out the
    same deadline again for every file in it.
    """
    root = git('rev-parse', '--show-toplevel')
    # Not by suffix: a conftest can collect tests from a file of any format, and a YAML case
    # read as unrunnable left the correction that changed it with no matrix asked. With no
    # pytest, a file that is not Python is no test pytest collects.
    python = path.endswith('.py')
    if not Path(root, path).is_file() or not python and importlib.util.find_spec('pytest') is None:
        return False
    answer = directory_answer(root, str(Path(path).parent) or '.', {} if asked is None else asked)
    if answer is None:
        return None
    if isinstance(answer, set):
        return path in answer
    found, failed = answer
    if path in found:
        return True
    # Named alone, a file of another format is collected even where the walk leaves it out, so
    # it is asked alone only when the walk says it is the file that failed, or a directory
    # holding it: a collect hook that raises fails the directory under the directory's own id.
    if not python and not {path, *(p.as_posix() for p in Path(path).parents)} & failed:
        return False
    return asked_alone(root, path, python)


def directory_answer(root, where, asked):
    """What collecting this directory answered, asked once per `asked`: the files collected, or
    after a failed collect the pair `walked` returns, or None where no collect could answer.

    A collect that ran out of time answered nothing, and the file alone collecting fine would
    then read as "not a test module": the gate opened on a neighbour that loops on import.
    """
    import review_matrix
    if where not in asked:
        try:
            asked[where] = set(review_matrix.nodes(root, [where]))
        except review_matrix.Unfinished:
            asked[where] = None
        except SystemExit:
            try:
                asked[where] = review_matrix.walked(root, [where])
            except (SystemExit, review_matrix.Unfinished):
                asked[where] = None
    return asked[where]


def asked_alone(root, path, python):
    """What pytest says of this file named on its own, once its directory could not answer.

    Named alone, a Python file always collects, so collecting fine says only that it is not the
    file that failed: not a test module. A file of another format that nothing collects is
    refused as matching no collector, which is an answer; one a plugin collects and cannot load
    fails another way, which is not.
    """
    import review_matrix
    try:
        found = review_matrix.ids(root, [path])
    except review_matrix.Unfinished:
        return None
    except SystemExit as refusal:
        return False if not python and re.search(NO_COLLECTOR, str(refusal)) else None
    return not python and bool(found)


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


def failing_before(base, changed, names):
    """The nodes of these test files that do not pass before the fix, and the files and nodes
    that could not be asked: the head's copy of each file, run node by node against the base's
    tree.

    A regression claims to fail before its fix, and this asks exactly that. Which nodes a delta
    added cannot answer it: an edited regression exists on both sides, so it is demanded
    nothing. A node that fails or errors here is this correction's to prove, and must have
    caught a mutant. A node that passes here is not demanded, since a correction that repairs a
    test and no code has none that fails; its added nodes are demanded anyway.

    A file the base tree cannot collect — it imports what the fix adds — cannot say which of
    its nodes the fix concerns: demanding all of them would ask its unrelated neighbours to
    catch a mutant, which nobody could satisfy. It is left to the added-node rule, and named;
    so is a file the base tree collects no node from. A node the head collects and the base
    tree does not — one defined only under a flag the fix adds — was never run there, and is
    named by its id. The head's side of that comparison is collected in the working checkout,
    as tests_added() collects it, which costs one more collect per changed file.

    An unpacked tree has no .git, so a test that reads the repository fails in it whatever the
    fix. A node counts only if the head, unpacked the same way, runs it and passes: a skip exits
    zero too, and a regression the fix skips proves nothing about it.
    """
    import review_matrix
    root = git('rev-parse', '--show-toplevel')
    here = [name for name in names if Path(root, name).is_file()]
    failing, unread = [], []
    if not here:
        return failing, unread
    with archived(base) as older:
        overlaid(older, root, base, changed)
        for name in here:
            nodes = collected_before(older, name)
            if not nodes:
                unread.append(name)
                continue
            unread += absent_before(root, name, nodes)
            for node in nodes:
                code, tail = review_matrix.run_case(older, None, [node])
                if review_matrix.outcome(code, tail) != 'passed':
                    failing.append(node)
    if failing:
        with archived('HEAD') as newer:
            failing = [node for node in failing if review_matrix.ran_alone(newer, [node])]
    return sorted(failing), unread


def overlaid(older, root, base, changed):
    """Lay the head's test paths over the unpacked previous tree, which is then the base's code
    under the head's tests.

    Every test path the delta changed is copied, not only the files asked: a conftest or a
    helper the head's tests need is a test path pytest collects nothing from, and the base's
    copy of it would fail them for a reason that is not the fix. Every test the delta deleted is
    removed, for the same reason: a conftest the head no longer has still ran there. A deleted
    test is what removed_tests() calls one, named like a test or collected at the base, so a
    file the project names its own way goes too.
    """
    removed = [name for name in git_raw('diff', '-z', '--name-only', '--no-renames', '--diff-filter=D',
                                        base, 'HEAD').split('\0') if name]
    for name in removed_tests(base, removed):
        unlinked(older, name).unlink(missing_ok=True)
    for name in [name for name in changed if Path(root, name).is_file()]:
        target = unlinked(older, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(root, name), target)


def collected_before(older, name):
    """The node ids the overlaid previous tree collects from this file, or none where it could
    not collect it: either way nothing of the file was asked there."""
    import review_matrix
    try:
        return review_matrix.ids(older, [name])
    except (SystemExit, review_matrix.Unfinished):
        return []


def absent_before(root, name, before):
    """The node ids the head collects from this file and the previous tree, `before`, does not.
    A head that cannot collect the file alone names none."""
    import review_matrix
    try:
        now = review_matrix.ids(root, [name])
    except (SystemExit, review_matrix.Unfinished):
        return []
    return sorted(set(now) - set(before))


def unlinked(older, name):
    """Where a file of the head goes in the unpacked tree, with every component on the way made
    the kind the head has there, and nothing followed: a link is removed, since a copy through
    one wrote outside the tree, and so is a file where the head has a directory or a directory
    where the head has the file, since the copy raised on either."""
    where = Path(older)
    parts = Path(name).parts
    for depth, part in enumerate(parts, 1):
        where = where / part
        if where.is_symlink() or (where.is_file() and depth < len(parts)):
            where.unlink()
        elif where.is_dir() and depth == len(parts):
            shutil.rmtree(where)
    return where


@contextlib.contextmanager
def archived(revision):
    """That revision's tree, unpacked outside the repository. Out of the object store rather
    than through a worktree, so nothing is added to this repository's bookkeeping and no
    checkout of it is touched."""
    # The archive sits beside the tree it unpacks, never in it: a tracked tree.tar at the root
    # was written over it and then deleted with it.
    box = tempfile.mkdtemp()
    try:
        where, packed = Path(box, 'tree'), Path(box, 'tree.tar')
        where.mkdir()
        with packed.open('wb') as handle:
            subprocess.run(['git', 'archive', revision], stdout=handle, check=True,
                           cwd=git('rev-parse', '--show-toplevel'))
        subprocess.run(['tar', '-xf', str(packed), '-C', str(where)], check=True)
        yield str(where)
    finally:
        shutil.rmtree(box, ignore_errors=True)


def caught_with_the_changed_test(kept, wanted):
    """Every test this correction added, and every changed test that fails before it, must be a
    test that caught something.

    Every, not one of them: a file is credited when any node of it failed, which an older
    neighbour of the new test satisfies, and one added test that catches would carry the
    vacuous one beside it.
    """
    # Whole ids: an added parameter of an older test is a node of its own, and without its
    # parameters it was credited by the parameter beside it.
    failed = {node for r in kept.get('results') or [] for node in (r.get('nodes') or [])}
    idle = [node for node in wanted if node not in failed]
    require(not idle, 'The recorded matrix caught nothing with %s, which this correction adds or '
            'which fails before it: %s failed under a mutant and %s did not. A test that already '
            'discriminated proves nothing about the one added or edited beside it.'
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
