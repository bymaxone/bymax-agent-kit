"""Gate layer: the ship-evidence block /bymax-pm:portfolio tells a model to run reads its record whole.

The block in `references/evidence.md` is run as written, with `gh`, `npm` and `curl` replaced by
stubs that answer only for the exact arguments the block should send. So a record read into the
wrong fields shows up as a wrong verdict, never as a lucky one. No test reaches the network.
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


def run_rows(rows, **env):
    """Run the block over `rows` and return its output lines.

    The record's file name and field delimiter are the ones the block itself declares, so
    the test follows the documented format instead of repeating it.
    """
    block = evidence_block()
    name = re.search(r'\.run/([A-Za-z0-9_.]+)"', block).group(1)
    delimiter = '|' if "IFS='|'" in block else '\t'
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run = root / 'work/.claude/portfolio/.run'
        run.mkdir(parents=True)
        (run / name).write_text(''.join(delimiter.join(row) + '\n' for row in rows))
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

    def test_a_health_url_must_be_http(self):
        """curl would read a `file:` URL from disk, so only an http(s) URL is requested."""
        lines, _ = run_rows([('deployment', 'acme/app', '', 'staging', 'file:///etc/hostname')],
                            STUB_NO_DEPLOYMENTS='1')
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('REFUSED'), lines[0])


if __name__ == '__main__':
    unittest.main()
