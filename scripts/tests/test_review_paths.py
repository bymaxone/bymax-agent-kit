"""The campaign's readers of changed test paths, against paths git quotes when it prints them
one to a line. A quoted path matches no file, so each reader has to ask git for NUL-separated
output, where a path is spelled as itself."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_claims
import review_evidence
import review_git

FLOW = ROOT / 'plugins/bymax-quality/scripts/review_flow.py'


class QuotedTestPathTests(unittest.TestCase):
    """Git quotes a non-ASCII path it prints one to a line, and every reader of changed tests
    matched the quoted spelling against real ones: tests/test_café.py was no test."""

    def test_each_reader_of_changed_tests_reads_a_quoted_path_as_itself(self):
        where = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, where, True)

        def git(*args):
            return subprocess.run(['git', '-C', str(where), *args], check=True, capture_output=True,
                                  text=True).stdout.strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.email', 'a@b.invalid')
        git('config', 'user.name', 'A')
        (where / 'tests').mkdir()
        (where / 'tests' / 'test_gone_é.py').write_text('def test_gone(): pass\n')
        git('add', '-A')
        git('commit', '-qm', 'base')
        base = git('rev-parse', 'HEAD')
        git('switch', '-qc', 'side')
        (where / 'tests' / 'test_side_ñ.py').write_text('def test_side(): pass\n')
        git('add', '-A')
        git('commit', '-qm', 'side')
        git('switch', '-q', 'main')
        (where / 'tests' / 'test_café.py').write_text('def test_cafe(): pass\n')
        (where / 'tests' / 'test_gone_é.py').unlink()
        git('add', '-A')
        git('commit', '-qm', 'the correction')
        git('merge', '-q', '--no-ff', '-m', 'merge side', 'side')
        head = git('rev-parse', 'HEAD')
        here = os.getcwd()
        os.chdir(where)
        self.addCleanup(os.chdir, here)
        self.assertEqual(review_evidence.tests_changed(base, head),
                         (['tests/test_café.py'], ['tests/test_gone_é.py']))
        self.assertEqual(review_evidence.merged_in_tests(base, head), ['tests/test_side_ñ.py'])


def commit_with(where, base, files):
    """A commit on top of `base` holding these files, byte names to byte contents, built without
    the worktree: a filesystem such as APFS refuses a name that is not valid UTF-8, while a
    commit made on Linux carries one and a clone of it has to be read anyway."""
    env = dict(os.environ, GIT_INDEX_FILE=str(where / '.git' / 'scratch-index'),
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
               GIT_AUTHOR_NAME='A', GIT_AUTHOR_EMAIL='a@b.invalid',
               GIT_COMMITTER_NAME='A', GIT_COMMITTER_EMAIL='a@b.invalid')
    run = lambda *a, **k: subprocess.run(['git', '-C', str(where), *a], check=True,
                                          capture_output=True, env=env, **k).stdout.strip()
    run('read-tree', base)
    for name, content in files.items():
        blob = run('hash-object', '-w', '--stdin', input=content).decode()
        run('update-index', '--add', '--index-info', input=b'100644 ' + blob.encode() + b'\t' + name + b'\n')
    tree = run('write-tree').decode()
    return run('commit-tree', tree, '-p', base, '-m', 'bytes').decode()


class NotUtf8Tests(unittest.TestCase):
    """A name or a line that is not valid UTF-8 — a Latin-1 name committed on Linux, a Latin-1
    source — raised UnicodeDecodeError out of the first strict read, and the campaign stopped on
    a repository it had every reason to review."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.where, True)
        here = os.getcwd()
        os.chdir(self.where)
        self.addCleanup(os.chdir, here)
        self.git('init', '-q', '-b', 'main')
        self.git('commit', '-q', '--allow-empty', '-m', 'base')
        self.base = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                   GIT_AUTHOR_NAME='A', GIT_AUTHOR_EMAIL='a@b.invalid',
                   GIT_COMMITTER_NAME='A', GIT_COMMITTER_EMAIL='a@b.invalid')
        return subprocess.run(['git', *args], cwd=self.where, check=True, capture_output=True,
                              text=True, env=env).stdout.strip()

    def test_a_latin1_test_name_is_read_and_names_the_same_file_to_git(self):
        """The name comes back with its byte kept as a surrogate escape, and handed to git again
        it resolves the same blob: git still finds it."""
        head = commit_with(self.where, self.base, {b'tests/test_caf\xe9.py': b'def test_x(): pass\n'})
        self.assertEqual(review_evidence.tests_changed(self.base, head), (['tests/test_caf\udce9.py'], []))
        self.assertEqual(review_git.git('cat-file', '-p', head + ':tests/test_caf\udce9.py'),
                         'def test_x(): pass')

    def test_the_claims_checker_reads_the_prose_of_a_latin1_name(self):
        """A replaced byte names no file, so both sides of the name read empty and its prose
        went unread; kept as an escape, the head side is read."""
        head = commit_with(self.where, self.base, {b'notes-caf\xe9.md': b'The `OLD_NAME` flag.\n'})
        name = 'notes-caf\udce9.md'
        self.assertIn(name, review_claims.touched(self.base, head))
        self.assertIn('OLD_NAME', review_claims.sides(name, self.base, head)[1])

    def test_a_definition_that_survives_in_a_latin1_file_is_not_retired(self):
        """The names `git grep -l` lists keep a Latin-1 byte as a surrogate escape, so the file
        still defining the name is found, and `retired()` does not report it removed."""
        base = commit_with(self.where, self.base, {b'a.py': b'OLD_NAME = 1\n', b'other\xe9.py': b'OLD_NAME = 1\n',
                                                     b'README.md': b'Call `OLD_NAME` first.\n'})
        head = commit_with(self.where, base, {b'a.py': b'x = 1\n'})
        self.assertEqual(review_claims.retired(base, head, cwd=str(self.where)), [])

    def test_a_latin1_line_reaches_the_claude_reviewer(self):
        """The Claude adapter hands its reviewer the full diff, and a Latin-1 line in it raised
        before the reviewer ran. It arrives as UTF-8, with that byte spelled out."""
        sys.path.insert(0, str(ROOT / 'scripts/tests'))
        import test_review_flow
        bench = test_review_flow.FlowBench('setUp')
        bench.setUp()
        self.addCleanup(bench.doCleanups)
        (bench.repo / 'legacy.txt').write_bytes(b'caf\xe9\n')
        bench.commit('latin-1 line')
        state = bench.start(autonomous=True)
        for command in state['required_checks']:
            bench.flow('check', '--', *command)
        directory = self.where / 'bin'
        directory.mkdir()
        capture = self.where / 'prompt.txt'
        report = dict(status='completed', head=state['head'], base=state['review_base'],
                      summary='read', findings=[], resolutions=[])
        binary = directory / 'claude'
        binary.write_text('#!%s\nimport sys, json, pathlib\n'
                          'pathlib.Path(%r).write_bytes(sys.stdin.buffer.read())\n'
                          'print(json.dumps(dict(structured_output=%r, is_error=False)))\n'
                          % (sys.executable, str(capture), report))
        binary.chmod(0o755)
        env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ['PATH'])
        env.pop('CLAUDECODE', None)
        run = subprocess.run([sys.executable, str(FLOW), 'claude'], cwd=bench.repo, env=env,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(b'+caf\\xe9\n', capture.read_bytes())
        capture.read_bytes().decode('utf-8')

    def test_a_branch_name_that_is_not_utf8_locates_its_campaign(self):
        """A branch is named by bytes, and one that is not UTF-8 raised before any campaign step
        could run. Its directory is the digest of those bytes, so a UTF-8 branch keeps the
        directory it always had and a campaign started before is still found."""
        import hashlib
        import review_flow
        common = Path(review_git.git('rev-parse', '--git-common-dir')).resolve() / 'bymax-review'
        (self.where / '.git' / 'HEAD').write_bytes(b'ref: refs/heads/caf\xe9\n')
        self.assertEqual(review_flow.location(),
                         common / hashlib.sha256(b'refs/heads/caf\xe9').hexdigest())
        self.git('symbolic-ref', 'HEAD', 'refs/heads/feature/café')
        self.assertEqual(review_flow.location(),
                         common / hashlib.sha256('refs/heads/feature/café'.encode()).hexdigest())

    def test_a_branch_name_that_is_not_utf8_is_named_as_a_branch(self):
        """work_branch() and branch_ref() read a ref as strict UTF-8 and raised on such a name, so
        a start told its base branch could not run on it."""
        import review_flow
        with open(self.where / '.git' / 'packed-refs', 'ab') as packed:
            packed.write(b'%s refs/heads/caf\xe9\n' % self.base.encode())
        self.assertEqual(review_flow.branch_ref(os.fsdecode(b'caf\xe9')), 'refs/heads/caf\udce9')
        (self.where / '.git' / 'HEAD').write_bytes(b'ref: refs/heads/caf\xe9\n')
        self.assertEqual(review_flow.work_branch(), 'refs/heads/caf\udce9')
        self.assertEqual(review_flow.branch_ref('main'), 'refs/heads/main')

    def test_the_command_line_prints_a_name_that_is_not_utf8(self):
        """What the runtime prints — a prompt — can carry such a name as an escape,
        which a strict stdout refuses; it is printed as the bytes of the name."""
        script = ('import sys; sys.path.insert(0, %r)\n'
                  'import review_flow\n'
                  'review_flow.main = lambda: print("tests/test_caf\\udce9.py")\n'
                  'review_flow.cli()\n' % str(FLOW.parent))
        run = subprocess.run([sys.executable, '-c', script], capture_output=True, timeout=30,
                             env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, b'tests/test_caf\xe9.py\n')

    def test_the_claims_command_line_prints_a_name_that_is_not_utf8(self):
        """Reviewers are told to run review_claims.py on the delta, and its inventory names each
        file that added prose. A strict stdout refused such a name as a surrogate escape; it is
        printed as the bytes of the name. PYTHONIOENCODING makes stdout strict whatever the
        locale, as a UTF-8 locale other than C.UTF-8 does."""
        head = commit_with(self.where, self.base, {b'notes-caf\xe9.md': b'# Notes\n\nThis sentence has more than six words.\n'})
        run = subprocess.run([sys.executable, str(FLOW.with_name('review_claims.py')), self.base, head],
                             cwd=self.where, capture_output=True, timeout=60,
                             env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(b'notes-caf\xe9.md: This sentence has more than six words.', run.stdout)


class ReaderTextTests(unittest.TestCase):
    """What a reviewer's stdin receives, and what a digest reads, for a name that is not UTF-8."""

    def test_a_reader_is_handed_valid_utf8_with_the_byte_spelled_out(self):
        """Codex refuses stdin that is not valid UTF-8 before any model reads it, so handing it the
        original bytes spent every attempt on a candidate carrying such a name."""
        text = review_git.for_a_reader('Tests changed: tests/test_caf\udce9.py and caf\u00e9.md')
        self.assertEqual(text, 'Tests changed: tests/test_caf\\xe9.py and caf\u00e9.md')
        text.encode('utf-8')

    def test_under_a_latin1_locale_the_reader_gets_what_git_gave(self):
        """git_raw() reads through the filesystem encoding, so under Latin-1 a UTF-8 name arrives
        as two characters, and the runtime's own em dashes cannot be encoded back through it at
        all. Each reaches the reader as itself."""
        from unittest import mock
        with mock.patch.object(review_git.sys, 'getfilesystemencoding', return_value='iso8859-1'):
            text = review_git.for_a_reader('check \u2014 caf\u00c3\u00a9.md and plain ascii')
        self.assertEqual(text, 'check \u2014 caf\u00e9.md and plain ascii')

    def test_the_context_reaches_the_reader_as_its_author_wrote_it_under_a_latin1_locale(self):
        """The context is JSON the author wrote, and every reader of it treats its text as git_raw()
        text: for_a_reader() encodes it back through the filesystem encoding, and a check's
        arguments reach the child through the same. Read by the locale instead, a Latin-1 locale on
        a system whose filesystem encoding is UTF-8 handed the reviewers `IntenÃ§Ã£o` for
        `Intenção`. Run in a child under that locale, skipped where the system has none."""
        where = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, where, True)
        context = where / 'context.json'
        context.write_bytes(json.dumps(dict(intent='Inten\u00e7\u00e3o \u2014 kept', acceptance=['a'],
                                            measured=['m'], constraints=['c'], scope='s',
                                            checks=[['echo', 'caf\u00e9']]), ensure_ascii=False).encode('utf-8'))
        script = ('import json, locale, os, sys; sys.path.insert(0, %r)\n'
                  'import review_flow\n'
                  'text, checks = review_flow.context_contract(%r)\n'
                  'print(json.dumps(dict(locale=locale.getpreferredencoding(False),\n'
                  '    reader=review_flow.for_a_reader(text), argument=list(os.fsencode(checks[0][1])))))\n'
                  % (str(FLOW.parent), str(context)))
        env = dict(os.environ, LC_ALL='en_US.ISO8859-1', PYTHONUTF8='0')
        env.pop('PYTHONIOENCODING', None)
        run = subprocess.run([sys.executable, '-c', script], capture_output=True, env=env, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        seen = json.loads(run.stdout)
        if seen['locale'].replace('-', '').lower() not in ('iso88591', 'latin1'):
            self.skipTest('this system has no en_US.ISO8859-1 locale')
        self.assertIn('Inten\u00e7\u00e3o \u2014 kept', seen['reader'])
        self.assertEqual(bytes(seen['argument']), 'caf\u00e9'.encode('utf-8'))

    def test_a_digest_names_a_file_whose_name_is_not_utf8(self):
        """The digest a prose record binds to encoded each name strictly, so a Latin-1 file that
        added prose stopped the pass. Skipped where the filesystem refuses such a name."""
        import review_matrix
        where = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, where, True)
        try:
            descriptor = os.open(os.path.join(os.fsencode(str(where)), b'caf\xe9.py'), os.O_CREAT | os.O_WRONLY)
        except OSError:
            self.skipTest('this filesystem refuses a name that is not UTF-8')
        os.write(descriptor, b'x = 1\n')
        os.close(descriptor)
        self.assertEqual(len(review_matrix.digest(str(where), ['caf\udce9.py'])), 64)


if __name__ == '__main__':
    unittest.main()
