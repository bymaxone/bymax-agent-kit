"""Gate layer: the blocks /bymax-pm:portfolio tells a model to run read their record lists whole.

The ship-evidence block in `references/evidence.md` and the collector block in
`references/review.md` are run as written, with the tools they call (`gh`, `npm`, `curl`,
the collector) replaced by stubs that answer only for the arguments the block should send.
So a record read into the wrong fields shows up as a wrong verdict, never as a lucky one. No test reaches the network.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'plugins/bymax-pm/skills/portfolio/references/evidence.md'
BLOCK = re.compile(r'```bash\n(.*?)```', re.S)
# gh answers only the endpoints a correct read asks for. A deployment lookup for any
# environment other than `prod` finds nothing, which is what a mis-split record produces.
STUBS = {
    'gh': r'''#!/bin/bash
case "$2" in
  repos/acme/app) echo main ;;
  repos/acme/app/releases/tags/v1.0.0) echo v1.0.0 ;;
  repos/acme/app/compare/main...v1.0.0) echo behind ;;
  "repos/acme/app/deployments?environment=prod&per_page=1")
    [ -n "$STUB_NO_DEPLOYMENTS" ] || echo 42 ;;
  "repos/acme/app/deployments/42/statuses?per_page=1") echo success ;;
esac
''',
    'npm': '#!/bin/bash\n[ "$2" = "pkg@1.0.0" ] && echo 1.0.0\nexit 0\n',
    'curl': '#!/bin/bash\n[ "${!#}" = "https://acme.test/health" ] && printf 200 || printf 000\n',
}


def evidence_block():
    """The fenced block that reads the ship record, the one this suite exercises."""
    found = [block for block in BLOCK.findall(EVIDENCE.read_text()) if 'while IFS=' in block]
    assert len(found) == 1, f'expected one record-reading block, found {len(found)}'
    return found[0]


def run_rows(rows, final_newline=True, **env):
    """Run the block over `rows` and return its output lines.

    The record's file name and field delimiter are the ones the block itself declares, so
    the test follows the documented format instead of repeating it. `final_newline=False`
    writes the file the way the file tool does when handed text with no trailing newline.
    """
    block = evidence_block()
    name = re.search(r'\.run/([A-Za-z0-9_.]+)"', block).group(1)
    delimiter = '|' if "IFS='|'" in block else '\t'
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run = root / 'work/.claude/portfolio/.run'
        run.mkdir(parents=True)
        text = '\n'.join(delimiter.join(row) for row in rows)
        (run / name).write_text(text + ('\n' if final_newline else ''))
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        for tool, body in STUBS.items():
            (bin_dir / tool).write_text(body)
            (bin_dir / tool).chmod(0o755)
        environment = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'HOME': str(root),
                       'BYMAX_PORTFOLIO_DIR': str(root / 'work'), **env}
        done = subprocess.run(['bash', '-c', block], env=environment, capture_output=True, text=True)
    return done.stdout.splitlines(), done


class ShipEvidenceBlockTests(unittest.TestCase):
    """What the evidence block prints for each documented record shape."""

    def test_deployment_with_no_version_is_read_by_its_environment(self):
        """A deployment row has no version, and its empty field must stay a field.

        A whitespace delimiter collapsed it, so the environment landed in the version slot,
        the lookup asked for the health URL as an environment, and a real deployment read
        as unshipped. The verdict must come from the `prod` deployment's success status.
        """
        lines, _ = run_rows([('deployment', 'acme/app', '', 'prod', 'https://acme.test/health')])
        self.assertEqual(lines, ['SHIPPED deployment acme/app prod (42)'])

    def test_deployment_without_a_listed_deployment_falls_back_to_the_health_url(self):
        """With no deployment on record, the health URL in its own field decides."""
        lines, _ = run_rows([('deployment', 'acme/app', '', 'prod', 'https://acme.test/health')],
                            STUB_NO_DEPLOYMENTS='1')
        self.assertEqual(lines, ['SHIPPED deployment acme/app prod (health https://acme.test/health returned 200)'])

    def test_npm_and_release_rows_keep_their_trailing_empty_fields(self):
        """Rows that leave the last fields empty are still read."""
        lines, _ = run_rows([('npm', 'pkg', '1.0.0', '', ''),
                             ('github-release', 'acme/app', 'v1.0.0', '', ''),
                             ('npm', 'pkg', '9.9.9', '', '')])
        self.assertEqual(lines, ['SHIPPED npm pkg@1.0.0', 'SHIPPED github-release acme/app@v1.0.0',
                                 'NOT-SHIPPED npm pkg@9.9.9'])

    def test_store_build_is_never_shipped_by_a_read(self):
        """A store build counts only from a recorded human confirmation, never from this block."""
        lines, _ = run_rows([('store-build', 'ios-production', '1.4.0', '', '')])
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('HUMAN-ONLY store-build'), lines[0])

    def test_a_dash_in_any_field_is_refused_not_only_in_the_first(self):
        """The refusal covers every field, since the health URL is handed to curl as an argument.

        Checking the fields joined together looked only at the first character of the target,
        so a later field that started with a dash went through.
        """
        rows = [('deployment', 'acme/app', '', 'prod', '-oops'),
                ('npm', 'pkg', '-1.0.0', '', ''),
                ('npm', '-pkg', '1.0.0', '', '')]
        lines, _ = run_rows(rows)
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertTrue(line.startswith('REFUSED'), line)

    def test_a_value_holding_the_separator_is_refused(self):
        """An extra field would be folded into the health URL and sent to curl as part of it."""
        lines, _ = run_rows([('npm', 'pkg', '1.0.0', '', 'https://acme.test/health|extra')])
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('REFUSED'), lines[0])

    def test_a_last_record_without_a_final_newline_is_still_read(self):
        """`read` returns non-zero on an unterminated last line, so a bare `while read` loop
        skipped it and the deliverable vanished from the output instead of being reported."""
        lines, _ = run_rows([('npm', 'pkg', '1.0.0', '', ''), ('npm', 'pkg', '9.9.9', '', '')],
                            final_newline=False)
        self.assertEqual(lines, ['SHIPPED npm pkg@1.0.0', 'NOT-SHIPPED npm pkg@9.9.9'])

    def test_a_health_url_must_be_http(self):
        """curl would read a `file:` URL from disk, so only an http(s) URL is requested."""
        lines, _ = run_rows([('deployment', 'acme/app', '', 'staging', 'file:///etc/hostname')],
                            STUB_NO_DEPLOYMENTS='1')
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('REFUSED'), lines[0])


REVIEW = ROOT / 'plugins/bymax-pm/skills/portfolio/references/review.md'


def run_collector_block(repos, final_newline=True):
    """Run the review collector block over `repos` with a stub collector; return its status rows.

    The stub sits where the block looks for the sibling `bymax-report` plugin, and writes its
    `--out` file, so the block's own wiring (period, list, status file) is what is exercised.
    A repository is a directory with a `.git` entry; one named `broken` makes the stub fail.
    """
    blocks = [b for b in BLOCK.findall(REVIEW.read_text()) if 'while IFS= read -r REPO' in b]
    assert len(blocks) == 1, f'expected one collector block, found {len(blocks)}'
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin = root / 'cache/market/bymax-pm/1.1.0'
        plugin.mkdir(parents=True)
        collector = root / 'cache/market/bymax-report/1.2.0/scripts/collect.py'
        collector.parent.mkdir(parents=True)
        collector.write_text(
            'import sys\nout = sys.argv[sys.argv.index("--out") + 1]\n'
            'open(out, "w").write("{}")\n'
            'sys.exit(1 if "broken" in sys.argv[sys.argv.index("--repo") + 1] else 0)\n')
        run = root / 'work/.claude/portfolio/.run'
        run.mkdir(parents=True)
        paths = []
        for name in repos:
            if name != 'missing':
                (root / name / '.git').mkdir(parents=True)
            paths.append(str(root / name))
        (run / 'period.txt').write_text('last-week\n')
        (run / 'repos.txt').write_text('\n'.join(paths) + ('\n' if final_newline else ''))
        environment = {**os.environ, 'HOME': str(root), 'BYMAX_PORTFOLIO_DIR': str(root / 'work'),
                       'CLAUDE_PLUGIN_ROOT': str(plugin)}
        subprocess.run(['bash', '-c', blocks[0]], env=environment, capture_output=True, text=True)
        status = run / 'collect/status.tsv'
        rows = [line.split('\t') for line in status.read_text().splitlines()] if status.exists() else []
    return [(row[0], Path(row[1]).name, row[2]) for row in rows]


class ReviewCollectorBlockTests(unittest.TestCase):
    """What the review collector block records for each repository in its list."""

    def test_each_repository_gets_a_status_row_and_unreadable_ones_are_named(self):
        """A checkout the machine lacks and a collector that fails are rows, never silence."""
        self.assertEqual(run_collector_block(['alpha', 'missing', 'broken']),
                         [('1', 'alpha', 'ok'), ('2', 'missing', 'no-checkout'), ('3', 'broken', 'failed')])

    def test_a_last_repository_without_a_final_newline_is_still_collected(self):
        """An unterminated last line made `read` fail, so that repository got no row at all."""
        self.assertEqual(run_collector_block(['alpha', 'beta'], final_newline=False),
                         [('1', 'alpha', 'ok'), ('2', 'beta', 'ok')])


if __name__ == '__main__':
    unittest.main()
