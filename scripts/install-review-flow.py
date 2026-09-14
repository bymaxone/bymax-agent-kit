#!/usr/bin/env python3
"""Installation layer: back up and install the local Claude review policy and hook."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import shlex

ROOT = Path(__file__).resolve().parents[1]
BEGIN = '<!-- bymax-review:begin -->'
END = '<!-- bymax-review:end -->'


def backup(path, target, root):
    """Copy existing user material into a private rollback directory."""
    if path.exists():
        dest = target / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(path, dest)


def policy(text):
    """Replace the known review section while preserving unrelated user instructions."""
    replacement = BEGIN + '\n' + (ROOT / 'personal/review-policy.md').read_text().strip() + '\n' + END
    if BEGIN in text:
        before, rest = text.split(BEGIN, 1)
        if END not in rest:
            raise ValueError('Incomplete managed review policy markers.')
        return before + replacement + rest.split(END, 1)[1]
    old = '## Code review antes de QUALQUER push'
    following = '## Comentário de review em PR'
    if old in text:
        start = text.index(old)
        if following not in text[start:]:
            raise ValueError('Cannot delimit the existing review policy safely.')
        return text[:start] + replacement + '\n\n' + text[text.index(following, start):]
    return replacement + '\n\n' + text


LEGACY_HOOKS = ('code-review-require.sh', 'code-review-record.sh', 'bymax-review/review_push.py')


def superseded(command):
    """Identify a hook this installer replaces, refusing to guess at compound commands."""
    if not any(name in command for name in LEGACY_HOOKS):
        return False
    # Dropping the whole entry would silently delete the unrelated actions chained to it.
    if any(shell in command for shell in ('&&', '||', ';', '|', '\n')):
        raise ValueError('Hook command mixes the review guard with other actions; '
                         'migrate it by hand: ' + command)
    return True


def hook_settings(settings, hook):
    """Remove only the named legacy hooks and register one replacement Bash guard."""
    hooks = settings.setdefault('hooks', {})
    for event in ('PreToolUse', 'PostToolUse'):
        entries = []
        for group in hooks.get(event, []):
            kept = [h for h in group.get('hooks', []) if not superseded(h.get('command', ''))]
            if kept:
                entries.append(dict(group, hooks=kept))
        if event in hooks:
            hooks[event] = entries
    command = 'python3 ' + shlex.quote(str(hook))
    hooks.setdefault('PreToolUse', []).append(dict(matcher='Bash', hooks=[dict(
        type='command', command=command, timeout=15)]))
    return settings


def overlays(home, backup_dir):
    """Overlay installed user plugin files without changing registry or marketplace source."""
    registry = home / 'plugins/installed_plugins.json'
    if not registry.exists():
        raise ValueError('Install the Bymax quality and workflow plugins with Claude first.')
    plugins = json.loads(registry.read_text())['plugins']
    targets = []
    for name in ('bymax-quality', 'bymax-workflow'):
        entries = [i for i in plugins.get(name + '@bymax-claude-code', []) if i.get('scope') == 'user']
        if len(entries) != 1:
            raise ValueError('Expected exactly one installed user plugin: ' + name)
        path = Path(entries[0]['installPath']).resolve()
        if not path.is_relative_to((home / 'plugins/cache').resolve()) or not path.is_dir():
            raise ValueError('Unexpected plugin cache path: ' + str(path))
        targets.append((name, path))
    for name, path in targets:
        backup(path, backup_dir, home)
        shutil.copytree(ROOT / 'plugins' / name, path, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
        print('Local source overlay installed:', path)


def install(home, overlay):
    """Apply a prevalidated policy/settings merge with recoverable file backups."""
    home = home.resolve()
    settings_path, policy_path = home / 'settings.json', home / 'CLAUDE.md'
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    updated_policy = policy(policy_path.read_text() if policy_path.exists() else '')
    runtime = home / 'bymax-review'
    updated_settings = hook_settings(settings, runtime / 'review_push.py')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup_dir = home / 'backups' / ('bymax-review-' + stamp)
    backup_dir.mkdir(parents=True, mode=0o700)
    paths = [settings_path, policy_path, runtime, home / 'hooks/code-review-clear.sh']
    for path in paths:
        backup(path, backup_dir, home)
    if overlay:
        overlays(home, backup_dir)
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ('review_flow.py', 'review_push.py', 'review-report.schema.json'):
        shutil.copy2(ROOT / 'plugins/bymax-quality/scripts' / name, runtime / name)
    settings_path.write_text(json.dumps(updated_settings, indent=2) + '\n')
    policy_path.write_text(updated_policy)
    legacy = home / 'hooks/code-review-clear.sh'
    if legacy.exists():
        legacy.write_text('#!/usr/bin/env bash\n# Review adapter: explicit evidence replaces assertion-only clearance.\n'
                          'echo "Use review_flow.py finish after both reports, triage and gates." >&2\nexit 2\n')
    print('Backups:', backup_dir)
    print('Installed bounded review policy and hook. Restart Claude to reload plugin content.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude-home', type=Path, default=Path.home() / '.claude')
    parser.add_argument('--local-plugin-overlay', action='store_true',
                        help='Copy source into installed user plugin caches; official updates can replace it.')
    args = parser.parse_args()
    install(args.claude_home, args.local_plugin_overlay)
