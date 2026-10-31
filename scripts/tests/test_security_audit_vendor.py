"""Regression layer: the vendored Cloudflare security-audit skill stays the upstream skill.

`plugins/bymax-qa/skills/security-audit/` ships the upstream files unchanged so that the
installed skill does what the original does. This module pins that: every copied file must
match the SHA-256 recorded in `upstream.json`, nothing may be added or dropped beside it, and
the upstream validator suites must pass where Node is installed.

Run as a script with `--write-manifest <commit>` to rewrite `upstream.json` after a refresh.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'plugins/bymax-qa/skills/security-audit'
MANIFEST = SKILL / 'upstream.json'
SUITES = ('validate-findings.test.cjs', 'validate-coverage-ledger.test.cjs')
_SPEC = importlib.util.spec_from_file_location('vendor_manifest',
                                               ROOT / 'scripts/lib/vendor_manifest.py')
vendor_manifest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vendor_manifest)
digest = vendor_manifest.digest


def copied(skill=SKILL):
    """The upstream files of `skill`, the vendored folder by default."""
    return vendor_manifest.copied(skill)


def write_manifest(commit):
    """Record the upstream commit and the hash of every copied file."""
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else {}
    manifest.update({
        'repository': 'https://github.com/cloudflare/security-audit-skill',
        'commit': commit,
        'path': 'skills/security-audit',
        'license_path': 'LICENSE',
        'files': {name: digest(path) for name, path in copied().items()},
    })
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')


class SecurityAuditVendorTests(unittest.TestCase):
    """The installed security-audit skill is the upstream skill, byte for byte."""

    def manifest(self):
        """The recorded upstream identity."""
        return json.loads(MANIFEST.read_text())

    def test_the_manifest_names_one_upstream_commit(self):
        """A refresh without a recorded commit leaves no way to diff against upstream."""
        manifest = self.manifest()
        self.assertRegex(manifest['commit'], r'^[0-9a-f]{40}$')
        self.assertEqual(manifest['repository'], 'https://github.com/cloudflare/security-audit-skill')

    def test_every_copied_file_matches_its_upstream_hash(self):
        """An edit to a vendored file changes what the skill does without anyone deciding to."""
        recorded = self.manifest()['files']
        present = copied()
        self.assertEqual(sorted(present), sorted(recorded),
                         'files were added to or removed from the vendored skill')
        for name, path in present.items():
            with self.subTest(file=name):
                self.assertEqual(digest(path), recorded[name], f'{name} differs from upstream')

    def test_the_skill_keeps_its_entrypoint_license_and_validators(self):
        """The skill loads from SKILL.md and its workflow runs both validators by path."""
        present = copied()
        for name in ('SKILL.md', 'LICENSE', 'report-schema.json',
                     'validate-findings.cjs', 'validate-coverage-ledger.cjs', *SUITES):
            self.assertIn(name, present)
        self.assertIn('MIT License', (SKILL / 'LICENSE').read_text())

    def test_a_changed_file_is_caught(self):
        """The hash check is proved against a copy with one byte changed, not trusted."""
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        target = scratch / 'security-audit'
        shutil.copytree(SKILL, target)
        schema = target / 'report-schema.json'
        schema.write_bytes(schema.read_bytes() + b' ')
        recorded = self.manifest()['files']
        drifted = [name for name, path in copied(target).items() if digest(path) != recorded[name]]
        self.assertEqual(drifted, ['report-schema.json'])

    def test_a_file_added_in_a_subfolder_is_caught(self):
        """A file in a subfolder ships with the skill, so the file-set check has to see it.

        The listing read only the top level, so a nested addition left the set equal to the
        manifest and every case green.
        """
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        target = scratch / 'security-audit'
        shutil.copytree(SKILL, target)
        (target / 'extra').mkdir()
        (target / 'extra' / 'NOTE.md').write_text('added\n')
        # Only the top-level `OWN` files are this repository's own; a file with one of those
        # names deeper down is an addition like any other.
        (target / 'extra' / 'ATTRIBUTION.md').write_text('added\n')
        present = copied(target)
        self.assertIn('extra/NOTE.md', present)
        self.assertIn('extra/ATTRIBUTION.md', present)
        self.assertNotEqual(sorted(present), sorted(self.manifest()['files']))

    def test_the_upstream_validator_suites_pass(self):
        """The validators the skill runs still pass their own suites.

        Node is installed in CI, where this case is required. Locally a machine without it
        skips the case and says so.
        """
        node = shutil.which('node')
        if node is None:
            if os.environ.get('CI'):
                self.fail('node is required in CI to run the security-audit validator suites')
            self.skipTest('node is not installed; the security-audit validator suites did not run')
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        run = subprocess.run([node, '--test', *(str(SKILL / name) for name in SUITES)],
                             cwd=scratch, capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stdout[-4000:] + run.stderr[-4000:])


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--write-manifest':
        write_manifest(sys.argv[2])
    else:
        unittest.main()
