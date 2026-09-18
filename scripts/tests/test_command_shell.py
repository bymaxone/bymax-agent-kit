"""Gate layer: the shell a command file tells a model to run is checked, not just read.

A command file is a contract with a model, and its fenced shell is the part of that
contract a machine can verify. Reviewers read prose and disagree about it; these tests
decide. Each rule here exists because its absence produced a defect: a block that read a
variable an earlier fence assigned resolved the wrong base, and a block that asked the
reader to paste a ref into shell source would execute a ref name containing `$( )`.
"""
import ast
import io
import json
import os
from pathlib import Path
import re
import tokenize
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BLOCK = re.compile(r'```bash\n(.*?)```', re.S)
READ = re.compile(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\b')
ASSIGN = re.compile(r'(?:^|[;&|(]\s*)\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=', re.M)
FOR_LOOP = re.compile(r'^\s*for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b', re.M)
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
PLACEHOLDER = re.compile(r'<[A-Za-z][A-Za-z0-9_ .#-]*>')
# Names a block may read without assigning: the environment gives them, or the shell does.
AMBIENT = {'HOME', 'PWD', 'IFS', 'PATH', 'SHELL', 'USER', 'TMPDIR', 'EDITOR', 'PAGER',
           'GIT_TERMINAL_PROMPT', 'GIT_SSH_COMMAND', 'CLAUDE_PLUGIN_ROOT'}
# A value a reader is told to paste becomes shell source: git accepts `$( )` in ref names,
# and quoting does not rescue it. Double quotes keep a command substitution live, and single
# quotes end at the first apostrophe — which a name the user typed may carry. So no quoting
# is accepted here: a value the model supplies is written to a file with the file tool and
# read back, the way push.md and babysit-pr do. Two spellings ask for a paste: an empty
# assignment with a `<-` comment, and an assignment whose value holds a placeholder in any
# quoting. `export` prefixes an assignment exactly as ASSIGN already allows.
PASTE = re.compile(r'^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*='
                   r'(?:(?:""|\'\')\s*#.*<-|[\'"]?<[^>]*>)', re.M)


HANDOFF = re.compile(r'\$\(git rev-parse --git-dir\)/(bymax-[a-z-]+)')
# The redirection is what makes a line a write, and it may sit on its own continuation
# line, so the arrow is what this reads rather than the command name.
PRODUCES = re.compile(r'>\s*"\$\(git rev-parse --git-dir\)/(bymax-[a-z-]+)"')


def orphan_handoffs(pairs, scripts):
    """Handoff files a document reads that nothing writes first.

    Three things count as a producer: an earlier block in the same document, a plugin
    script (the best one, since the runtime records what it froze rather than a model
    being asked to type it), and the model's own file tool for a value only the model
    has. That last one is a contract, so the block has to declare it by name — a rule
    that accepted any mention of the file tool was satisfied by a sentence left over
    from an earlier design, and passed with no producer at all.
    """
    written, orphans = set(), []
    for _, block in sorted(pairs):
        for line in block.splitlines():
            produced = set(PRODUCES.findall(line))
            for name in set(HANDOFF.findall(line)) - produced:
                if name in written or f'{name} is written with the file tool' in block:
                    continue
                if any(f"'{name}'" in script for script in scripts):
                    continue
                orphans.append(name)
            written |= produced
    return sorted(set(orphans))


def documents():
    """Every command and skill document that carries runnable shell."""
    return sorted(path for pattern in ('plugins/*/commands/*.md', 'plugins/*/skills/**/*.md')
                  for path in ROOT.glob(pattern))


def blocks(path):
    """The fenced bash blocks of one document, numbered as they appear."""
    return list(enumerate(BLOCK.findall(path.read_text()), start=1))


def bound_by_read(body):
    """Names `read` binds: its trailing bare words, past any flags and their arguments."""
    names = set()
    for line in body.splitlines():
        for part in re.split(r'\bread\b', line)[1:]:
            for token in re.split(r'[;|&]', part)[0].split():
                if NAME.match(token):
                    names.add(token)
    return names


def code(block):
    """The block's executable lines: comments and blank lines carry no shell."""
    return '\n'.join(line for line in block.splitlines()
                     if line.strip() and not line.strip().startswith('#'))


class CommandShellTests(unittest.TestCase):
    """What a command file tells a model to run must hold on its own."""

    def test_documents_are_found(self):
        """A glob that matches nothing would make every rule below vacuous."""
        found = documents()
        self.assertTrue(found)
        self.assertIn(ROOT / 'plugins/bymax-pr/commands/push.md', found)
        self.assertTrue(any(blocks(path) for path in found))

    def test_no_block_reads_state_an_earlier_block_left(self):
        """Shell state does not cross a fence: each block assigns what it reads.

        A model runs each block in its own shell. A block that reads `$DEFAULT_REF` from
        an earlier fence sees it empty and takes the wrong branch silently.
        """
        for path in documents():
            for number, block in blocks(path):
                body = code(block)
                assigned = set(ASSIGN.findall(body)) | set(FOR_LOOP.findall(body)) | AMBIENT
                assigned |= bound_by_read(body)
                unassigned = {name for name in READ.findall(body) if name not in assigned}
                self.assertFalse(unassigned, f'{path.relative_to(ROOT)} block {number} reads '
                                             f'{sorted(unassigned)} without assigning it')

    def test_no_block_asks_the_reader_to_paste_a_value_into_shell(self):
        """A pasted value is shell source; git accepts `$( )` and backticks in ref names."""
        for path in documents():
            for number, block in blocks(path):
                self.assertNotRegex(block, PASTE, f'{path.relative_to(ROOT)} block {number} '
                                                  'asks for a value to be pasted into shell')

    def test_the_paste_rule_covers_both_spellings_that_ask_for_one(self):
        """The rule is what stands between a document and a ref name that carries `$( )`.

        No quoting rescues a pasted value: double quotes keep a command substitution
        live, and single quotes end at the first apostrophe. So every quoting is caught,
        and the value reaches shell through a file handoff instead.
        """
        for asked in ('DEFAULT_REF=""   # <- the ref Step 0 resolved',
                      "DEFAULT_REF=''  # <- the ref Step 0 resolved",
                      'RUN_ID=<the failed run id>',
                      "RUN_ID='<the failed run id>'",
                      'RUN_ID="<the failed run id>"',
                      'export RUN_ID=<the failed run id>',
                      'RANGE=<review_base>..<head>'):
            self.assertRegex(asked, PASTE, f'{asked!r} asks for a paste and is not caught')
        for safe in ('RUN_ID=$(cat run-id)', 'echo "<placeholder in prose>"',
                     'DEFAULT_REF=$(sed -n 1p handoff)', 'RUN_ID=$(gh run list -q .id)'):
            self.assertNotRegex(safe, PASTE, f'{safe!r} is not a paste and is refused')


    def test_the_gate_block_refuses_an_absent_scope_and_previews_a_dirty_one(self):
        """An empty scope must refuse, because an empty scope reads as a clean review.

        `git diff HEAD` on a clean tree matches nothing, so every check in the gate would
        find nothing and report success. That is the failure the block guards: with no
        campaign to ask about, only a dirty tree has something to review, and HEAD is its
        scope.
        """
        block = None
        for _, candidate in blocks(ROOT / 'plugins/bymax-quality/commands/code-review.md'):
            if 'review_flow.py" range' in candidate:
                block = candidate
        self.assertIsNotNone(block, 'the mechanical gate no longer asks the runtime for its scope')
        resolution = block[:block.index('\nfi') + 3]
        fixture = Path(tempfile.mkdtemp())
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        subprocess.run(['git', 'init', '-q', str(fixture)], env=env, check=True)
        for setting, value in (('user.name', 'fixture'), ('user.email', 'f@x.invalid')):
            subprocess.run(['git', 'config', setting, value], cwd=fixture, env=env, check=True)
        (fixture / 'f').write_text('1\n')
        subprocess.run(['git', 'add', 'f'], cwd=fixture, env=env, check=True)
        subprocess.run(['git', 'commit', '-qm', 'c'], cwd=fixture, env=env, check=True)

        def run():
            return subprocess.run(['bash', '-c', resolution + '\necho "[$RANGE]"'],
                                  cwd=fixture, env=env, capture_output=True, text=True)

        clean = run()
        self.assertNotIn('[', clean.stdout, 'a clean tree with no campaign produced a scope')
        self.assertIn('nothing to read', clean.stderr)
        (fixture / 'f').write_text('dirty\n')
        self.assertEqual(run().stdout.strip(), '[HEAD]', 'a dirty preview lost its scope')

    def test_a_guard_accepts_every_value_its_own_document_prescribes(self):
        """A guard that refuses a documented value closes the path it was added to protect."""
        for relative, name, values in (
                ('plugins/bymax-pr/skills/babysit-pr/SKILL.md', 'RUN_ID', ('1234567890',)),):
            document = ROOT / relative
            # Every guard, not the first: a rule added below an `esac` used to sit outside
            # anything this examined.
            guards = [block for _, block in blocks(document) if f'case "${name}" in' in block]
            self.assertTrue(guards, f'{relative} has no {name} guard to exercise')
            for block in guards:
                case = block[block.index(f'case "${name}" in'):]
                case = case[:case.index('esac') + 4]
                for value in values:
                    script = f'{name}={value!r}\n{case}\necho ACCEPTED'
                    outcome = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
                    self.assertIn('ACCEPTED', outcome.stdout,
                                  f'{relative} guards {name} and refuses {value!r}, which the '
                                  'same document prescribes')

    def test_every_handoff_a_document_reads_is_written_by_that_document(self):
        """A read with no producer is a path that can only fail.

        The blocks are fences in one document and the model runs them in order, so the
        step that resolves a value is the one that has to record it. A handoff nobody
        writes made the flaky-rerun path exit on every invocation.
        """
        scripts = [script.read_text() for script in (ROOT / 'plugins').rglob('*.py')]
        for path in documents():
            orphans = orphan_handoffs(blocks(path), scripts)
            self.assertEqual(orphans, [], f'{path.relative_to(ROOT)} reads {orphans} and '
                                          'nothing writes that file first: no earlier block here, '
                                          'no plugin script, and no block declaring that the file '
                                          'tool writes that name')

    def test_the_producer_rule_fails_on_the_shape_it_exists_for(self):
        """A gate is only worth its rule if it fails on the defect; these are that defect.

        The rule's first spelling exempted any block mentioning the file tool, and the
        block reading the run id happened to carry that phrase from an earlier design.
        It passed with no producer at all. So the exemption now names its handoff, and
        each case below is one way the rule was or could be made vacuous.
        """
        read = ('RUN_ID=$(sed -n 1p "$(git rev-parse --git-dir)/bymax-babysit-run" '
                '2>/dev/null || true)')
        write = 'printf \'%s\\n\' "$RUN_ID" > "$(git rev-parse --git-dir)/bymax-babysit-run"'
        cases = (
            ('no producer at all', [(1, read)], ['bymax-babysit-run']),
            ('a generic mention of the file tool',
             [(1, '# write it with the file tool\n' + read)], ['bymax-babysit-run']),
            ('a producer in a later block', [(1, read), (2, write)], ['bymax-babysit-run']),
            ('a producer in an earlier block', [(1, write), (2, read)], []),
            ('the same block writing then reading', [(1, write + '\n' + read), ], []),
            ('an exemption naming the handoff',
             [(1, '# bymax-babysit-run is written with the file tool\n' + read)], []),
        )
        for label, pairs, expected in cases:
            self.assertEqual(orphan_handoffs(pairs, []), expected, f'the rule misjudges {label}')


    def test_every_handoff_read_is_guarded_before_the_value_is_used(self):
        """A handoff can be absent — a loop in flight, or an entry at a later phase.

        `|| true` keeps the block running on purpose, so the emptiness check is what
        stops it. Without one the empty value flows on: the babysit loop read no PR,
        found nothing failing and nothing unresolved, and announced the PR ready.
        """
        handoff = re.compile(r'\$\(git rev-parse --git-dir\)/bymax-[a-z-]+')
        seen = 0
        for path in documents():
            for number, block in blocks(path):
                for line in block.splitlines():
                    match = ASSIGN.search(line)
                    if not (match and handoff.search(line) and 'printf' not in line):
                        continue
                    seen += 1
                    # The value may be renamed before it is tested: push.md reads the
                    # default into DEFAULT_REF, lets it stand in for a missing upstream
                    # as BASE, and tests BASE. Follow the value, then require a test on
                    # one of the names it reached.
                    carriers = {match.group(1)}
                    for other in block.splitlines():
                        moved = ASSIGN.search(other)
                        if moved and any(f'${{{name}}}' in other or f'${name}' in other
                                         for name in carriers):
                            carriers.add(moved.group(1))
                    tests = [f'{form} "${spelling}"' for form in ('[ -z', '[ -n', 'case')
                             for name in carriers
                             for spelling in (name, '{' + name + '}')]
                    self.assertTrue(any(test in block for test in tests),
                                    f'{path.relative_to(ROOT)} block {number} reads the handoff '
                                    f'into {match.group(1)} and nothing checks whether it arrived')
        self.assertGreater(seen, 0, 'no handoff read found — the rule would pass vacuously')

    @unittest.skipUnless(shutil.which('shellcheck'), 'shellcheck is not installed')
    def test_runnable_blocks_pass_shellcheck(self):
        """A block with no placeholder is meant to run as written, so it must lint clean.

        Warnings and errors fail; info and style do not, since a command file legitimately
        quotes shell it hands to another interpreter. SC2034 is excluded for the same
        reason: a block may compute a value for the reader of the document to use. The
        fence says bash, so the block is linted as bash.
        """
        for path in documents():
            for number, block in blocks(path):
                if PLACEHOLDER.search(block):
                    continue
                result = subprocess.run(['shellcheck', '-s', 'bash', '--severity=warning', '-e', 'SC2034', '-'],
                                        input=block, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0,
                                 f'{path.relative_to(ROOT)} block {number}:\n{result.stdout}')


class PushCommandBehaviourTests(unittest.TestCase):
    """The blocks /bymax-pr:push depends on are run against real repositories."""

    def setUp(self):
        """Locate the blocks by what they compute, so renaming one fails here loudly."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        text = (ROOT / 'plugins/bymax-pr/commands/push.md').read_text()
        self.blocks = BLOCK.findall(text)
        self.resolve = self.block_with('bymax-push-default"\n')   # the block that writes it
        self.base = self.block_with('REVIEW_BASE=""')
        self.guard = self.block_with('skipping the PR')

    def block_with(self, needle):
        """The one block that carries this marker."""
        found = [block for block in self.blocks if needle in block]
        self.assertEqual(len(found), 1, f'expected exactly one block containing {needle!r}')
        return found[0]

    def repo(self, commits=2, branch='main'):
        """A repository with its own history, isolated from the machine's git config."""
        path = Path(self.temp.name) / f'r{len(list(Path(self.temp.name).iterdir()))}'
        subprocess.run(['git', 'init', '-q', '-b', branch, str(path)], env=self.env, check=True)
        for name, value in (('user.name', 'Fixture'), ('user.email', 'fixture@example.invalid')):
            subprocess.run(['git', 'config', name, value], cwd=path, env=self.env, check=True)
        for index in range(commits):
            (path / 'f').write_text(f'{index}\n')
            subprocess.run(['git', 'add', 'f'], cwd=path, env=self.env, check=True)
            subprocess.run(['git', 'commit', '-qm', f'c{index}'], cwd=path, env=self.env, check=True)
        return path

    def git(self, repo, *args):
        """Read git state in one fixture repository."""
        return subprocess.check_output(['git', *args], cwd=repo, env=self.env, text=True).strip()

    def run_block(self, block, repo, strict=True):
        """Run one documented block as a model would, and report status and output."""
        script = ('set -e\n' if strict else '') + block
        result = subprocess.run(['bash', '-c', script], cwd=repo, env=self.env,
                                capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def test_resolution_block_records_what_the_later_blocks_read(self):
        """Step 0 resolves the default branch once; the later blocks must find it."""
        repo = self.repo()
        self.git(repo, 'checkout', '-qb', 'feature')
        (repo / 'f').write_text('feature\n')
        self.git(repo, 'commit', '-qam', 'feature work')
        status, _, error = self.run_block(self.resolve, repo)
        self.assertEqual(status, 0, error)
        status, out, error = self.run_block(self.base, repo)
        self.assertEqual(status, 0, error)
        self.assertEqual(out, self.git(repo, 'rev-parse', 'main'))

    def test_base_is_an_ancestor_of_head_or_the_command_stops(self):
        """A base equal to HEAD would clear a receipt over an empty delta."""
        # A branch with no conventional name and no remote leaves Step 0 with no default,
        # so the base is the branch's root: with one commit that is HEAD, and the command
        # must stop rather than review an empty delta.
        for commits, expected in ((1, 'stops'), (2, 'base')):
            repo = self.repo(commits=commits, branch='work')
            self.run_block(self.resolve, repo)
            status, out, error = self.run_block(self.base, repo)
            if expected == 'stops':
                self.assertEqual(status, 1, out)
                self.assertIn('No review base', error)
            else:
                self.assertEqual(status, 0, error)
                self.assertEqual(out, self.git(repo, 'rev-parse', 'HEAD~1'))

    def test_unrelated_history_stops_instead_of_guessing(self):
        """merge-base gives nothing there, and no other commit may stand in for it."""
        repo = self.repo()
        self.git(repo, 'branch', '-M', 'main')
        self.git(repo, 'checkout', '-q', '--orphan', 'other')
        (repo / 'g').write_text('x\n')
        self.git(repo, 'add', 'g')
        self.git(repo, 'commit', '-qm', 'orphan root')
        self.run_block(self.resolve, repo)
        status, _, error = self.run_block(self.base, repo)
        self.assertEqual(status, 1)
        self.assertIn('No review base', error)

    def test_a_ref_name_carrying_a_command_substitution_stays_data(self):
        """git accepts `$( )` in a ref name; no block may let it run."""
        repo = self.repo()
        marker = Path(self.temp.name) / 'executed'
        self.git(repo, 'branch', f'evil$(touch${{IFS}}{marker})')
        self.git(repo, 'checkout', '-qb', 'work')
        (repo / 'f').write_text('work\n')
        self.git(repo, 'commit', '-qam', 'work')
        directory = Path(self.git(repo, 'rev-parse', '--git-dir'))
        handoff = (repo / directory if not directory.is_absolute() else directory) / 'bymax-push-default'
        handoff.write_text(f'evil$(touch${{IFS}}{marker})\nevil$(touch${{IFS}}{marker})\n')
        for block in (self.base, self.guard):
            self.run_block(block, repo, strict=False)
        self.assertFalse(marker.exists(), 'a ref name was executed as shell')

    def test_blocks_survive_a_missing_handoff_under_set_e(self):
        """A model may run any block first; reading what Step 0 did not write must not abort."""
        repo = self.repo()
        for block in (self.base, self.guard):
            status, _, error = self.run_block(block, repo)
            self.assertIn(status, (0, 1), error)
            self.assertNotIn('No such file', error)


class AutopilotTerminationTests(unittest.TestCase):
    """The failure modes an unattended chain can hit must be in the document it reads.

    A mode absent from that document gets improvised at three in the morning, and the
    improvisations available to this one — extend the budget, or branch for a fresh one —
    are precisely what the delivery ledger exists to prevent. These are prose gates: they
    cannot check that the chain behaves, only that the contract it follows still says so,
    which is the difference between a rule that was removed and a rule that was decided.
    """

    SKILL = ROOT / 'plugins/bymax-workflow/skills/autopilot/SKILL.md'

    def setUp(self):
        self.text = self.SKILL.read_text()
        self.table = self.text.split('## Termination summary')[1]

    def test_a_spent_review_budget_has_its_own_row(self):
        """The nearest existing row is about project gates failing repeatedly, which is a
        different event: a campaign that spends its candidate budget has passed its gates and
        is holding on a finding. Without a row of its own, the chain ends on the first phase
        whose review does not converge."""
        rows = [line for line in self.table.splitlines() if line.startswith('|')]
        budget = [line for line in rows if 'budget' in line.lower()]
        self.assertTrue(budget, 'no termination row names the review candidate budget')
        self.assertIn('park', ' '.join(budget).lower())

    def test_the_chain_never_extends_the_budget_on_its_own_authority(self):
        """Extending is a human decision by construction — check_extension accepts the flag
        only once the budget is actually spent — so every mention here must be a prohibition.

        Per clause, not per line. The first version of this asked whether "never" appeared
        anywhere on the line, and the line carries three of them for other things: inverting
        the prohibition to "Use --extend-delivery on the chain's own authority" left the whole
        suite green. Found by mutating the document, not by reading the assertion.
        """
        mentions = 0
        for line in self.text.splitlines():
            for clause in re.split(r'[,.;]', line):
                if '--extend-delivery' in clause:
                    mentions += 1
                    self.assertIn('never', clause.lower(), clause.strip())
        self.assertTrue(mentions, 'the skill no longer mentions the delivery extension at all')

    def test_phase_selection_reads_the_dependency_graph(self):
        """The graph exists in roadmap.template.md and the orchestrator never read it, which
        is the whole reason one blocked phase ended a run: the queue was sequential by
        convention, not by dependency."""
        step = self.text.split('### STEP 0')[1].split('###')[0]
        self.assertIn('Dependency graph', step)
        self.assertIn('transitive dependencies', step)
        # And parking is bounded, or a broken plan parks every phase in turn.
        self.assertRegex(step, r'(?i)\bthree\b.*parked|parked.*\bthree\b|Cap the parking')


class ProseReferenceTests(unittest.TestCase):
    """A case name written in prose must name a case that exists.

    Two findings of the campaign that shipped the trigger rule were this: a docstring pointing
    at a case deleted in the same delta, and a sentence surviving in a third file after being
    corrected in two. Both were found by a reader, both were mechanical, and nothing checked
    them. A name is the one part of prose a machine can resolve, so it is the part that gets a
    gate — not because dangling names are the worst kind of wrong sentence, but because they
    are the kind a test can settle.

    Prose means docstrings, comments and markdown OUTSIDE fenced code blocks. Two exclusions,
    both of them measured rather than guessed. A string literal is data the author hands to
    something — a probe entry's example pytest invocation names a case in an imagined project —
    and is not a claim about this repository. A fenced block is an example for the reader, and
    the protocol's triage sample cites a case in somebody else's tree; that one was a false
    positive this gate reported on the real package before it was narrowed.

    The gate then reported a third, and the third was this docstring: naming an example is
    indistinguishable, to a matcher, from claiming it. So the examples above are described and
    not spelled, and the two cases below demonstrate the exclusions with synthetic names where
    the gate cannot see them. A gate that has to be exempted from itself has a blind spot
    exactly where its author writes.
    """

    NAME = re.compile(r'\btest_[a-z0-9_]{6,}\b')
    FENCED = re.compile(r'```.*?```', re.S)

    @classmethod
    def known(cls):
        """Every case name this repository defines, plus the stems of its test modules."""
        files = sorted(set(list(ROOT.glob('scripts/tests/test_*.py'))
                           + list(ROOT.glob('codex/tests/test_*.py'))))
        names = {f.stem for f in files}
        for f in files:
            names |= set(re.findall(r'def (test_[A-Za-z0-9_]+)', f.read_text()))
        return names, files

    @classmethod
    def prose(cls, path):
        """What the file asserts in words: markdown minus its examples, or docs and comments."""
        if path.suffix == '.md':
            return cls.FENCED.sub(' ', path.read_text())
        source = path.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return ''
        parts = [ast.get_docstring(node) or '' for node in ast.walk(tree)
                 if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
        parts += [tok.string for tok in tokenize.generate_tokens(io.StringIO(source).readline)
                  if tok.type == tokenize.COMMENT]
        return '\n'.join(parts)

    @staticmethod
    def foreign(root=ROOT):
        """Tracked directories whose contents this repository did not write — derived, not listed.

        Two kinds, each with a marker the repository already maintains for its own reasons. A
        vendored tree carries ATTRIBUTION.md beside its LICENSE, which is how its origin is
        recorded. The Codex mirror is written by codex/scripts/bundle.py, which names its own
        destination in a constant.

        Derived because the hand-kept tuple moved twice and lost something each time: first it
        let the vendored trees be read, then, excluding their parent to keep them out, it took
        vendor/README.md with them — a document this repository wrote about why the folder
        exists. A list has to be remembered; a marker is already there.
        """
        # :(glob) or the pathspec is fnmatch: `*` would cross a separator and the start of a
        # basename, so a repository-authored docs/THIRD-PARTY-ATTRIBUTION.md would take its
        # whole directory out of the gate. And one marker is not proof: the vendoring
        # convention puts a LICENSE beside it, so both are required. A derivation that can
        # shrink this gate silently is worse than the list it replaced, because no one has to
        # edit anything for it to happen.
        listed = subprocess.run(['git', '-C', str(root), 'ls-files', '-z',
                                 '--', ':(glob)**/ATTRIBUTION.md'], capture_output=True)
        names = [n for n in os.fsdecode(listed.stdout).split('\0') if n]
        # The LICENSE is read from the index too: an untracked one, dropped in by anything at
        # all, must not be able to authorise an exclusion.
        everything = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True)
        tracked = {n for n in os.fsdecode(everything.stdout).split('\0') if n}
        roots = {str(Path(name).parent) + '/' for name in names
                 if str(Path(name).parent / 'LICENSE') in tracked}
        bundler = root / 'codex/scripts/bundle.py'
        if bundler.is_file():
            named = re.search(r"PACKAGE = ROOT / '([^']+)'", bundler.read_text())
            if named:
                roots.add(named.group(1) + '/')
        return sorted(roots)

    def sources(self):
        """Every document and script this repository authors: what git tracks, minus the mirror.

        Two wrong answers preceded this one. Six explicit globs claimed to be everything and
        missed 23 authored files, TESTING.md and REVIEW.md among them — the two whose purpose
        is naming this repository's test modules. Replacing them with rglob over the tree then
        read seven files git does not track: two pytest caches and five local audit artefacts
        the .gitignore calls local evidence. Authorship is a property of the index, not of the
        disk, so the index is what is asked.
        """
        listed = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', '*.md', '*.py'],
                                capture_output=True)
        names = [n for n in os.fsdecode(listed.stdout).split('\0') if n]
        skip = self.foreign()
        return sorted(ROOT / name for name in names
                      if not any(name.startswith(part) for part in skip)
                      and (ROOT / name).is_file())

    def test_what_is_foreign_is_derived_from_markers_the_repository_keeps(self):
        """A third vendored tree added tomorrow is excluded without anyone remembering to say so.

        The exclusion list was hand-kept and moved twice, losing something each time. It is
        derived now from two markers that exist for their own reasons: ATTRIBUTION.md, written
        beside a vendored tree's LICENSE to record where it came from, and the bundler's own
        PACKAGE constant, which names the mirror it generates. Asserted against a synthetic
        tree so the rule is tested rather than this repository's current contents.
        """
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        subprocess.run(['git', 'init', '-q', str(scratch)], check=True)
        (scratch / 'third-party/newcomer').mkdir(parents=True)
        (scratch / 'third-party/newcomer/ATTRIBUTION.md').write_text('taken from elsewhere\n')
        (scratch / 'third-party/newcomer/LICENSE').write_text('theirs\n')
        (scratch / 'third-party/README.md').write_text('why this folder exists\n')
        (scratch / 'codex/scripts').mkdir(parents=True)
        (scratch / 'codex/scripts/bundle.py').write_text(
            "ROOT = 1\nPACKAGE = ROOT / 'codex/plugins/somewhere'\n")
        subprocess.run(['git', '-C', str(scratch), 'add', '-A'], check=True)

        derived = self.foreign(scratch)
        self.assertIn('third-party/newcomer/', derived)
        self.assertIn('codex/plugins/somewhere/', derived)
        # The parent is not excluded, so a document the repository wrote about the folder stays
        # readable — which is what excluding the parent cost the last time this list moved.
        self.assertNotIn('third-party/', derived)
        # And a tree with no marker is not foreign, however it is named.
        (scratch / 'third-party/ours').mkdir()
        (scratch / 'third-party/ours/notes.md').write_text('written here\n')
        # Nor is one this repository wrote that merely mentions attribution in a filename: the
        # pathspec matches the marker and not a name ending in it, and a LICENSE must sit
        # beside it. Either alone would let an authored directory out of the gate.
        # This one carries a LICENSE too, so only the pathspec keeps it in: with an fnmatch
        # pathspec its name ends in the marker and the whole directory would leave the gate.
        # Each condition needs a shape where it is the only thing standing, or a mutation of
        # one is masked by the other — which is how the first version of this case passed
        # against a loosened pathspec.
        (scratch / 'docs').mkdir()
        (scratch / 'docs/THIRD-PARTY-ATTRIBUTION.md').write_text('who we credit\n')
        (scratch / 'docs/LICENSE').write_text('ours\n')
        (scratch / 'notes').mkdir()
        (scratch / 'notes/ATTRIBUTION.md').write_text('no licence beside this one\n')
        # And one whose LICENSE is on disk but was never added. Without this shape the case
        # cannot tell the index from the filesystem at all — everything above is staged, so
        # both readings agree and a mutation from one to the other changes no answer.
        (scratch / 'dropped').mkdir()
        (scratch / 'dropped/ATTRIBUTION.md').write_text('claims to be vendored\n')
        subprocess.run(['git', '-C', str(scratch), 'add', '-A'], check=True)
        (scratch / 'dropped/LICENSE').write_text('untracked, and so not this repository saying so\n')
        derived = self.foreign(scratch)
        self.assertNotIn('third-party/ours/', derived)
        self.assertNotIn('docs/', derived)
        self.assertNotIn('notes/', derived)
        self.assertNotIn('dropped/', derived)

    def test_no_prose_names_a_case_that_does_not_exist(self):
        """The gate itself. A deleted case leaves its name behind in whatever pointed at it,
        and the pointer reads as coverage that is no longer there — which is worse than no
        sentence at all, because the next reader stops looking."""
        known, files = self.known()
        self.assertGreater(len(files), 5, 'the test modules moved; this gate is reading nothing')
        self.assertGreater(len(known), 100, 'no case names were collected; the pattern broke')
        # The two documents whose purpose is naming test modules must be among the sources, or
        # the gate is blind where its subject is most written about — which it was.
        read = {str(path.relative_to(ROOT)) for path in self.sources()}
        # One statement, exact, and stated without consulting the derivation it checks. What
        # this repository authors is every tracked .md and .py except the three trees it does
        # not, and those three are written here as literals — the derivation's job is to arrive
        # at the same answer from markers, which its own case proves separately.
        #
        # Four partial rules stood here before and each let something through. A floor of 100
        # against 130 sources passed at 129, so a whole plugin could leave. Comparing top-level
        # directories asked foreign() for the expected side, so the mutant moved both, and
        # `plugins` survives while eight of nine plugins remain. Requiring each plugin to
        # contribute one file missed every shrink that is not plugin-shaped — all of scripts/,
        # or every plugins/*/skills/ — and misread a future plugins/README.md as a plugin. And
        # a floor beside any of them only catches a shrink large enough to cross it. Equality
        # catches all of them, in both directions, and needs no floor: a gate reading nothing
        # is a gate reading the wrong set.
        listed = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', '--', '*.md', '*.py'],
                                capture_output=True)
        every = {name for name in os.fsdecode(listed.stdout).split('\0') if name}
        VENDORED = ('vendor/ecc-skills/', 'vendor/ui-ux-pro-max/', 'codex/plugins/bymax-codex/')
        expected = {name for name in every
                    if not any(name.startswith(part) for part in VENDORED)}
        self.assertEqual(expected, read,
                         'the gate no longer reads exactly what this repository authors. Not '
                         'read: ' + str(sorted(expected - read)[:8]) + '; read but not ours or '
                         'not tracked: ' + str(sorted(read - expected)[:8]))
        dangling = {}
        for path in self.sources():
            for name in self.NAME.findall(self.prose(path)):
                if name not in known:
                    dangling.setdefault(name, set()).add(str(path.relative_to(ROOT)))
        self.assertFalse(dangling, 'prose names cases that do not exist: '
                         + '; '.join('%s in %s' % (n, ', '.join(sorted(w)))
                                     for n, w in sorted(dangling.items())))

    def test_the_gate_reads_prose_and_not_fixture_data(self):
        """Both exclusions, asserted rather than trusted: a name inside a plain string literal
        is data the author passes to something, and a name inside a fenced block is an example
        about somebody else's repository. Measured before this gate was written — the fenced
        one was a false positive it reported on the real tree."""
        scratch = Path(tempfile.mkdtemp())
        code = scratch / 'sample.py'
        code.write_text('"""A docstring naming test_a_real_case_name.\n\n'
                        'And a comment below."""\n'
                        '# see test_a_commented_case_name\n'
                        'PROBE = "pytest tests/x.py::test_a_literal_case_name"\n')
        seen = self.prose(code)
        self.assertIn('test_a_real_case_name', seen)
        self.assertIn('test_a_commented_case_name', seen)
        self.assertNotIn('test_a_literal_case_name', seen)

        document = scratch / 'sample.md'
        document.write_text('Prose naming test_a_documented_case_name.\n\n'
                            '```json\n{"evidence": "reproduced with test_a_fenced_case_name"}\n```\n')
        seen = self.prose(document)
        self.assertIn('test_a_documented_case_name', seen)
        self.assertNotIn('test_a_fenced_case_name', seen)


if __name__ == '__main__':
    unittest.main()
