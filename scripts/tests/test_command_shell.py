"""Gate layer: the shell a command file tells a model to run is checked, not just read.

A command file is a contract with a model, and its fenced shell is the part of that
contract a machine can verify. Reviewers read prose and disagree about it; these tests
decide. Each rule here exists because its absence produced a defect: a block that read a
variable an earlier fence assigned resolved the wrong base, and a block that asked the
reader to paste a ref into shell source would execute a ref name containing `$( )`.
"""
import json
import os
from pathlib import Path
import re
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


if __name__ == '__main__':
    unittest.main()
