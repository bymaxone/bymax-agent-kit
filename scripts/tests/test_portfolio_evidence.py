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
# The stubs answer only the endpoints a correct read asks for, apply the block's own `--jq`
# expression with the real jq (an expression that is wrong for an empty list fails here as it
# would against GitHub), and fail the way the real tools do: `gh` with "HTTP 404" for a missing
# object and another status for a service it cannot reach, `npm` with E404 for a missing version.
STUBS = {
    'gh': r'''#!/bin/bash
endpoint="$2"; expr=""
while [ $# -gt 0 ]; do [ "$1" = "--jq" ] && expr="$2"; shift; done
fail() { echo "$1" >&2; exit "$2"; }
[ -n "$STUB_GH_DOWN" ] && fail "gh: authentication required" 4
case "$endpoint" in
  repos/acme/app) json='{"default_branch":"main"}' ;;
  repos/acme/app/releases/tags/v1.0.0)
    [ -n "$STUB_NO_RELEASE" ] && fail "gh: Not Found (HTTP 404)" 1
    json='{"tag_name":"v1.0.0"}' ;;
  repos/acme/app/compare/main...v1.0.0) json="{\"status\":\"${STUB_COMPARE:-behind}\"}" ;;
  "repos/acme/app/deployments?environment=prod&per_page=1")
    if [ -n "$STUB_NO_DEPLOYMENTS" ]; then json='[]'; else json='[{"id":42}]'; fi ;;
  "repos/acme/app/deployments/42/statuses?per_page=1")
    [ -n "$STUB_STATUS_DOWN" ] && fail "gh: HTTP 502" 1
    json="[{\"state\":\"${STUB_DEPLOY_STATE:-success}\"}]" ;;
  *) fail "gh: Not Found (HTTP 404)" 1 ;;
esac
if [ -n "$expr" ]; then echo "$json" | jq -r "$expr"; else echo "$json"; fi
''',
    'npm': r'''#!/bin/bash
case "$STUB_NPM" in
  down) exit 127 ;;
  e404) echo "npm error code E404" >&2; exit 1 ;;
esac
if [ "$2" = "pkg@1.0.0" ]; then echo 1.0.0; exit 0; fi
echo "npm error code E404" >&2; exit 1
''',
    'curl': r'''#!/bin/bash
if [ -n "$STUB_CURL_DOWN" ]; then printf 000; exit 7; fi
if [ "${!#}" = "https://acme.test/health" ]; then printf 200; else printf 000; fi
''',
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

    def test_a_read_that_cannot_run_is_unread_never_a_verdict(self):
        """npm that fails to run left an empty answer, and an empty answer equals an empty
        version: the block printed SHIPPED with no release behind it, or NOT-SHIPPED for a
        version it never looked up. A failed read is a gap in coverage, not a verdict."""
        lines, _ = run_rows([('npm', 'pkg', '1.0.0', '', '')], STUB_NPM='down')
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('UNREAD npm'), lines[0])

    def test_only_a_not_found_answer_is_a_negative_verdict(self):
        """A registry or API that answers "not found" is a read that ran, so it is NOT-SHIPPED."""
        lines, _ = run_rows([('npm', 'pkg', '9.9.9', '', ''), ('github-release', 'acme/app', 'v1.0.0', '', '')],
                            STUB_NPM='e404', STUB_NO_RELEASE='1')
        self.assertEqual(lines, ['NOT-SHIPPED npm pkg@9.9.9',
                                 'NOT-SHIPPED github-release acme/app@v1.0.0: no release for the tag'])

    def test_a_deliverable_with_no_version_is_undecided_not_read(self):
        """A deliverable with no version has nothing to look up, so nothing is read."""
        rows = [('npm', 'pkg', '', '', ''), ('github-release', 'acme/app', '', '', '')]
        lines, _ = run_rows(rows)
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertTrue(line.startswith('UNDECIDED'), line)

    def test_a_service_that_cannot_be_reached_is_unread_for_releases_and_deployments(self):
        """With gh unable to answer, no release or deployment verdict is derived from the silence."""
        lines, _ = run_rows([('github-release', 'acme/app', 'v1.0.0', '', ''),
                             ('deployment', 'acme/app', '', 'prod', '')], STUB_GH_DOWN='1')
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertTrue(line.startswith('UNREAD'), line)

    def test_a_tag_not_on_the_default_branch_is_not_shipped(self):
        """A tag that is ahead of or diverged from the default branch is not part of its history."""
        lines, _ = run_rows([('github-release', 'acme/app', 'v1.0.0', '', '')], STUB_COMPARE='ahead')
        self.assertEqual(lines, ['NOT-SHIPPED github-release acme/app@v1.0.0: the tag is not on main\'s history'])

    def test_a_status_read_that_fails_is_unread_and_a_failing_state_is_not_shipped(self):
        """A deployment whose status cannot be read is a gap; one whose latest state is not
        success is a read that ran and found it unshipped."""
        down, _ = run_rows([('deployment', 'acme/app', '', 'prod', '')], STUB_STATUS_DOWN='1')
        self.assertTrue(down[0].startswith('UNREAD deployment'), down[0])
        failed, _ = run_rows([('deployment', 'acme/app', '', 'prod', '')], STUB_DEPLOY_STATE='failure')
        self.assertEqual(failed, ['NOT-SHIPPED deployment acme/app prod: latest state failure'])

    def test_no_deployment_and_no_health_url_is_not_shipped_but_an_unreachable_health_url_is_unread(self):
        """An empty deployment list is an answer; a health URL that does not respond is not one."""
        none, _ = run_rows([('deployment', 'acme/app', '', 'prod', '')], STUB_NO_DEPLOYMENTS='1')
        self.assertEqual(none, ['NOT-SHIPPED deployment acme/app prod: no deployment for the environment'])
        down, _ = run_rows([('deployment', 'acme/app', '', 'prod', 'https://acme.test/health')],
                           STUB_NO_DEPLOYMENTS='1', STUB_CURL_DOWN='1')
        self.assertTrue(down[0].startswith('UNREAD deployment'), down[0])

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
