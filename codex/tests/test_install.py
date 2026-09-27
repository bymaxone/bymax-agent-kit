"""Installation integration tests: exercise the real CLI in a disposable Codex profile."""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skill_discovery import discover

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / 'scripts/install-codex.sh'


class InstallationTests(unittest.TestCase):
    """Protect installed-state verification, portability and marketplace ownership."""

    def setUp(self):
        """Use only a temporary profile; CI fails if the required CLI is unavailable."""
        if not shutil.which('codex'):
            if os.environ.get('BYMAX_REQUIRE_CODEX_TEST') == '1':
                self.fail('Codex CLI required for installation tests')
            self.skipTest('Codex CLI absent; isolated installation not exercised')
        self.temporary = tempfile.TemporaryDirectory(prefix='bymax-install-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'profile').mkdir()
        self.environment = dict(os.environ, CODEX_HOME=str(self.root / 'profile'))

    def run_command(self, command, success=True):
        """Run an isolated command and require the expected status, preserving diagnostics."""
        result = subprocess.run(command, env=self.environment, cwd=self.root,
                                capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_install_reinstall_check_and_portable_review(self):
        """A real installed package is enabled and its helper works in another repository."""
        first = self.run_command(['bash', str(INSTALLER)])
        self.assertIn('Installed cache verified:', first.stdout)
        self.run_command(['bash', str(INSTALLER)])
        self.run_command(['bash', str(INSTALLER), '--check'])
        listing = self.run_command(['codex', 'plugin', 'list', '--marketplace', 'bymax-codex', '--json'])
        installed = json.loads(listing.stdout)['installed']
        self.assertEqual(len(installed), 1)
        self.assertTrue(installed[0]['enabled'])
        self.verify_discovery()
        version = json.loads((ROOT / 'codex/plugins/bymax-codex/.codex-plugin/plugin.json').read_text())['version']
        cache = self.root / 'profile/plugins/cache/bymax-codex/bymax-codex' / version
        self.assertEqual(len(list((cache / 'skills').glob('*/SKILL.md'))), 28)
        self.run_command(['git', 'init', '-b', 'trunk'])
        (self.root / '.gitignore').write_text('profile/\n')
        (self.root / 'fixture.txt').write_text('portable\n')
        result = self.run_command(['python3', str(cache / 'scripts/review_scope.py')])
        evidence = json.loads(result.stdout)
        self.assertTrue(any(p['path'] == 'fixture.txt' for p in evidence['untracked']))

    def verify_discovery(self):
        """Require all native skills to be discoverable and enabled through the real loader."""
        result = asyncio.run(discover(self.environment, self.root))
        items = result['data']
        prefix = 'bymax-codex:'
        skills = [s for item in items for s in item['skills'] if s['name'].startswith(prefix)]
        catalog = json.loads((ROOT / 'codex/plugins/bymax-codex/references/catalog.json').read_text())
        self.assertEqual({s['name'] for s in skills}, {prefix + name for name in catalog})
        self.assertTrue(all(s['enabled'] for s in skills))
        errors = [e for item in items for e in item.get('errors', []) if 'bymax' in e.get('path', '')]
        self.assertEqual(errors, [])

    def test_dry_run_creates_no_codex_profile(self):
        """Preview validates sources but registers no marketplace or plugin."""
        result = self.run_command(['bash', str(INSTALLER), '--dry-run'])
        self.assertIn('Would install', result.stdout)
        self.assertEqual(list((self.root / 'profile').iterdir()), [])

    def test_check_does_not_install_missing_plugin(self):
        """Read-only checking fails on an absent installation without installing it."""
        self.run_command(['bash', str(INSTALLER), '--check'], success=False)
        self.assertFalse((self.root / 'profile/plugins/cache/bymax-codex').exists())

    def test_conflicting_marketplace_is_not_replaced(self):
        """A same-name marketplace in another checkout remains registered and unchanged."""
        other = self.root / 'other marketplace'
        shutil.copytree(ROOT / 'codex', other, ignore=shutil.ignore_patterns('__pycache__'))
        self.run_command(['codex', 'plugin', 'marketplace', 'add', str(other), '--json'])
        result = self.run_command(['bash', str(INSTALLER)], success=False)
        self.assertIn('already points elsewhere', result.stderr)
        listing = self.run_command(['codex', 'plugin', 'marketplace', 'list', '--json'])
        self.assertEqual(Path(json.loads(listing.stdout)['marketplaces'][0]['root']).resolve(), other.resolve())
