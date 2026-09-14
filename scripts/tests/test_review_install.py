"""Installation regression layer: preserve unrelated Claude configuration and backups."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class InstallTests(unittest.TestCase):
    """Exercise repeated installation against a synthetic Claude profile."""

    def test_preserves_unrelated_settings_and_idempotent_policy(self):
        """Install twice without duplicating the hook or losing other user instructions."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            # Absolute paths under this home, which is what the installer itself writes.
            original = dict(enabledPlugins={'unrelated': True}, hooks={
                'PreToolUse': [dict(matcher='Bash', hooks=[dict(command='other-check'),
                    dict(command=str(home / 'hooks/code-review-require.sh'))])],
                'PostToolUse': [dict(matcher='Skill', hooks=[
                    dict(command=str(home / 'hooks/code-review-record.sh'))])],
                'Stop': [dict(hooks=[dict(command='keep-stop-hook')])]})
            (home / 'settings.json').write_text(json.dumps(original))
            (home / 'CLAUDE.md').write_text('## Personal instructions\nKeep this material.\n')
            for _ in range(2):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                                         '--claude-home', tmp], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            settings = json.loads((home / 'settings.json').read_text())
            self.assertEqual(settings['enabledPlugins'], original['enabledPlugins'])
            self.assertEqual(settings['hooks']['Stop'], original['hooks']['Stop'])
            self.assertIn('other-check', json.dumps(settings))
            self.assertNotIn('code-review-record.sh', json.dumps(settings))
            self.assertEqual(json.dumps(settings).count('bymax-review/review_push.py'), 1)
            policy = (home / 'CLAUDE.md').read_text()
            self.assertEqual(policy.count('<!-- bymax-review:begin -->'), 1)
            self.assertIn('Keep this material.', policy)
            backups = list((home / 'backups').glob('*/settings.json'))
            self.assertEqual(len(backups), 2)
            self.assertTrue(any(json.loads(p.read_text()) == original for p in backups))

    def test_unrelated_hook_sharing_a_legacy_substring_survives(self):
        """Somebody else's script is not this installer's to remove, however it is named."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            # Same filename, same parent directory name, different owner: all must survive.
            others = ['/opt/hooks/audit-code-review-require.sh',
                      '/opt/unrelated/hooks/code-review-require.sh',
                      'python3 /opt/unrelated/bymax-review/review_push.py']
            (home / 'settings.json').write_text(json.dumps(dict(hooks={
                'PreToolUse': [dict(matcher='Bash', hooks=[dict(command=c) for c in others])]})))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                                     '--claude-home', tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            settings = json.dumps(json.loads((home / 'settings.json').read_text()))
            for command in others:
                self.assertIn(command, settings)
            self.assertEqual(settings.count(str(home / 'bymax-review/review_push.py')), 1)

    def test_legacy_name_as_an_argument_is_not_ownership(self):
        """Printing a hook's name is not invoking it, so the entry stays."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mentions = 'echo code-review-require.sh'
            (home / 'settings.json').write_text(json.dumps(dict(hooks={
                'PreToolUse': [dict(matcher='Bash', hooks=[dict(command=mentions)])]})))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                                     '--claude-home', tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(mentions, (home / 'settings.json').read_text())

    def test_compound_legacy_hook_is_not_silently_dropped(self):
        """A legacy guard chained to another action needs a hand migration, not deletion."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            settings = dict(hooks={'PreToolUse': [dict(matcher='Bash', hooks=[dict(
                command=str(home / 'hooks/code-review-require.sh') + ' && /opt/hooks/security-check.sh')])]})
            (home / 'settings.json').write_text(json.dumps(settings))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                                     '--claude-home', tmp], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('security-check.sh', result.stderr)
            self.assertEqual(json.loads((home / 'settings.json').read_text()), settings)
            self.assertFalse((home / 'CLAUDE.md').exists())

    def test_unknown_policy_boundary_is_not_overwritten(self):
        """An incomplete managed section fails before settings or policy change."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            text = '<!-- bymax-review:begin -->\nUnknown incomplete content'
            (home / 'CLAUDE.md').write_text(text)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                                     '--claude-home', tmp], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((home / 'CLAUDE.md').read_text(), text)
            self.assertFalse((home / 'settings.json').exists())
