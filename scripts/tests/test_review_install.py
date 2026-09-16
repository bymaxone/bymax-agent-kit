"""Installation regression layer: preserve unrelated Claude configuration and backups."""
import json
import os
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

    def test_background_chained_hook_is_not_silently_dropped(self):
        """A bare & separates commands too, so the entry needs a hand migration."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            settings = dict(hooks={'PreToolUse': [dict(matcher='Bash', hooks=[dict(
                command=str(home / 'hooks/code-review-require.sh') + ' & /opt/hooks/audit.sh')])]})
            (home / 'settings.json').write_text(json.dumps(settings))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                                     '--claude-home', tmp], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('audit.sh', result.stderr)
            self.assertEqual(json.loads((home / 'settings.json').read_text()), settings)

    def test_sections_between_the_policy_delimiters_survive(self):
        """Only the managed section is replaced; every other user heading is preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'CLAUDE.md').write_text(
                '# Global\n\n## Code review antes de QUALQUER push\nold\n\n'
                '## Deployment restrictions\nNEVER deploy on Friday.\n\n'
                '## Comentário de review em PR — NUNCA deixe em aberto\nkeep\n')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                                     '--claude-home', tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            policy = (home / 'CLAUDE.md').read_text()
            for kept in ('# Global', '## Deployment restrictions', 'NEVER deploy on Friday',
                         '## Comentário de review em PR', 'keep'):
                self.assertIn(kept, policy)
            self.assertNotIn('## Code review antes de QUALQUER push', policy)

    def test_installed_runtime_installs_the_hook(self):
        """A campaign started from the INSTALLED runtime places the pre-push hook.

        The fixtures elsewhere run the repository copy of review_flow.py, beside which
        the hook source always exists; only this path proves the deployed runtime ships it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'
            home.mkdir()
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                                     '--claude-home', str(home)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            runtime = home / 'bymax-review/review_flow.py'
            self.assertTrue((home / 'bymax-review/review_prepush.py').exists())
            repo = Path(tmp) / 'repo'
            repo.mkdir()
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=repo, env=env, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (repo / 'a').write_text('1')
            git('add', '.')
            git('commit', '-qm', 'base')
            base = git('rev-parse', 'HEAD')
            (repo / 'a').write_text('2')
            git('add', '.')
            git('commit', '-qm', 'candidate')
            context = Path(tmp) / 'context.json'
            context.write_text(json.dumps(dict(intent='i', acceptance=['a'], constraints=['c'],
                                               scope='s', checks=[[sys.executable, '-c', 'pass']])))
            result = subprocess.run([sys.executable, str(runtime), 'start', '--base', base,
                                     '--context', str(context)], cwd=repo, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            hook = repo / '.git/hooks/pre-push'
            self.assertTrue(hook.exists() and os.access(hook, os.X_OK), 'hook missing from real install')

    def _overlay_profile(self, home, marketplace):
        """Build a synthetic Claude profile whose plugin cache is keyed by one marketplace id."""
        registry = {'plugins': {}}
        for name in ('bymax-quality', 'bymax-workflow', 'bymax-pr'):
            install_path = home / 'plugins/cache' / marketplace / name
            (install_path / 'commands').mkdir(parents=True)
            (install_path / 'commands/stale.md').write_text('replaced by the overlay')
            registry['plugins'][name + '@' + marketplace] = [
                dict(scope='user', installPath=str(install_path))]
        (home / 'plugins').mkdir(parents=True, exist_ok=True)
        (home / 'plugins/installed_plugins.json').write_text(json.dumps(registry))
        return registry

    def test_overlay_finds_the_cache_under_either_marketplace_id(self):
        """The marketplace id moved, and an install keyed by either one still overlays."""
        for marketplace in ('bymax-agent-kit', 'bymax-claude-code'):
            with self.subTest(marketplace=marketplace), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                self._overlay_profile(home, marketplace)
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                     '--claude-home', tmp, '--local-plugin-overlay'],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                overlaid = home / 'plugins/cache' / marketplace / 'bymax-quality'
                self.assertTrue((overlaid / 'commands/code-review.md').exists())
                self.assertTrue((overlaid / 'scripts/review_flow.py').exists())

    def test_overlay_refuses_a_plugin_installed_under_both_marketplace_ids(self):
        """Two caches for one plugin is ambiguous, so the run ends before anything is written.

        The duplicate is the LAST name overlays() iterates: a run that validated and copied
        name by name would already have overlaid the earlier two and taken their backups
        before reaching the ambiguity, and duplicating the first name could not see that.
        """
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            registry = self._overlay_profile(home, 'bymax-agent-kit')
            legacy = home / 'plugins/cache/bymax-claude-code/bymax-pr'
            legacy.mkdir(parents=True)
            registry['plugins']['bymax-pr@bymax-claude-code'] = [
                dict(scope='user', installPath=str(legacy))]
            (home / 'plugins/installed_plugins.json').write_text(json.dumps(registry))
            result = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/install-review-flow.py'),
                 '--claude-home', tmp, '--local-plugin-overlay'],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('bymax-pr', result.stderr)
            # Nothing written: no cache overlaid, no backup taken, no runtime deployed.
            for name in ('bymax-quality', 'bymax-workflow', 'bymax-pr'):
                cache = home / 'plugins/cache/bymax-agent-kit' / name
                self.assertTrue((cache / 'commands/stale.md').exists(), name)
                self.assertFalse((cache / 'commands/code-review.md').exists(), name)
            self.assertFalse((legacy / 'commands').exists())
            self.assertFalse((home / 'backups').exists())
            self.assertFalse((home / 'bymax-review').exists())
            self.assertFalse((home / 'settings.json').exists())

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
