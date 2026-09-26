#!/usr/bin/env python3
"""Installation layer: back up and install the local Claude review policy and hook."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import shlex

ROOT = Path(__file__).resolve().parents[1]
MARKETPLACES = ('bymax-agent-kit', 'bymax-claude-code')
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
    if old in text:
        start = text.index(old)
        # The managed section ends at the next heading of any name: every user
        # section after it, whatever it is called, is preserved untouched.
        rest = text[start + len(old):]
        boundary = rest.find('\n## ')
        if boundary < 0:
            raise ValueError('Cannot delimit the existing review policy safely.')
        preserved = rest[boundary:].lstrip('\n')
        return text[:start] + replacement + '\n\n' + preserved
    return replacement + '\n\n' + text


LEGACY_HOOKS = ('hooks/code-review-require.sh', 'hooks/code-review-record.sh',
                'bymax-review/review_push.py')
RUNNERS = {'python', 'python3', 'bash', 'sh', 'zsh'}


def managed(home):
    """Return the absolute paths this installer places under the selected home."""
    return {(home / relative).resolve() for relative in LEGACY_HOOKS}


def invokes_legacy(words, home):
    """Match a hook this installer owns: the invoked path, under this Claude home.

    Neither a shared filename nor a shared parent directory establishes ownership --
    `/opt/unrelated/hooks/code-review-require.sh` and
    `python3 /opt/unrelated/bymax-review/review_push.py` are somebody else's tools,
    and `echo code-review-require.sh` only prints a name.
    """
    if not words:
        return False
    runner = Path(words[0]).name in RUNNERS and len(words) > 1
    invoked = Path(words[1] if runner else words[0])
    return invoked.is_absolute() and invoked.resolve() in managed(home)


def superseded(command, home):
    """Identify a hook this installer replaces, refusing to guess at compound commands."""
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    if not invokes_legacy(words, home):
        return False
    # Dropping the whole entry would silently delete the unrelated actions chained to it.
    # A bare & is a command separator like the others: what runs alongside the hook
    # is not ours to remove.
    if any(shell in command for shell in ('&&', '||', ';', '|', '&', '\n')):
        raise ValueError('Hook command mixes the review guard with other actions; '
                         'migrate it by hand: ' + command)
    return True


def hook_settings(settings, hook, home):
    """Remove only the named legacy hooks and register one replacement Bash guard."""
    hooks = settings.setdefault('hooks', {})
    for event in ('PreToolUse', 'PostToolUse'):
        entries = []
        for group in hooks.get(event, []):
            kept = [h for h in group.get('hooks', []) if not superseded(h.get('command', ''), home)]
            if kept:
                entries.append(dict(group, hooks=kept))
        if event in hooks:
            hooks[event] = entries
    command = 'python3 ' + shlex.quote(str(hook))
    hooks.setdefault('PreToolUse', []).append(dict(matcher='Bash', hooks=[dict(
        type='command', command=command, timeout=15)]))
    return settings


def overlay_targets(home):
    """Resolve every installed plugin cache to overlay, or raise before anything is written."""
    registry = home / 'plugins/installed_plugins.json'
    if not registry.exists():
        raise ValueError('Install the Bymax quality, workflow and PR plugins with Claude first.')
    plugins = json.loads(registry.read_text())['plugins']
    targets = []
    for name in ('bymax-quality', 'bymax-workflow', 'bymax-pr'):
        # An install predating the marketplace rename keys its cache entry under the
        # old id, so both ids must resolve to the one installed user plugin.
        installed = [i for marketplace in MARKETPLACES
                     for i in plugins.get(name + '@' + marketplace, [])]
        entries = [i for i in installed if i.get('scope') == 'user']
        if len(entries) != 1:
            raise ValueError('Expected exactly one installed user plugin: ' + name)
        path = Path(entries[0]['installPath']).resolve()
        if not path.is_relative_to((home / 'plugins/cache').resolve()) or not path.is_dir():
            raise ValueError('Unexpected plugin cache path: ' + str(path))
        targets.append((name, path))
    return targets


def overlays(targets, home, backup_dir):
    """Overlay resolved plugin caches without changing registry or marketplace source."""
    for name, path in targets:
        backup(path, backup_dir, home)
        shutil.copytree(ROOT / 'plugins' / name, path, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
        print('Local source overlay installed:', path)


def payload(root=None):
    """Every file the runtime needs beside review_flow.py, read from the package.

    Derived rather than listed. A hand-kept tuple decided this until now, and a runtime
    script nobody copies is a gate that does not exist — silently, because the flow imports
    it only when the case it guards occurs. `.sh` is excluded deliberately: codex-review.sh
    is a repository entrypoint, not part of the runtime planted in $HOME.
    """
    where = (root or ROOT) / 'plugins/bymax-quality/scripts'
    return sorted(path for path in where.iterdir()
                  if path.suffix in ('.py', '.json') and path.is_file())


def complete(carried):
    """Refuse a short payload or an untracked extra before the first write, by what git tracks.

    Deriving what to copy removed the one thing the hand-kept tuple did well: failing when a
    file was absent. An installer that reports success while planting a runtime missing a
    module leaves every repository unguarded, silently.

    The expected set is not a second hand-kept list — that was the first correction here, and
    it named three files while review_flow imports five, so the guard passed on a payload that
    could not be imported. It is the package's own tracked contents.
    """
    listed = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', '--',
                             'plugins/bymax-quality/scripts'], capture_output=True)
    tracked = {name.split('/')[-1] for name in os.fsdecode(listed.stdout).split('\0')
               if name.endswith(('.py', '.json'))}
    # An unchecked exit made the expectation empty outside a checkout — a `git archive`
    # export would install a payload missing review_flow.py itself and report success. An
    # expectation nothing could answer is not an expectation.
    if listed.returncode != 0 or not tracked:
        raise SystemExit('Refusing to install: this package is not a git checkout, so what it '
                         'should carry cannot be read. Install from a clone.')
    names = {path.name for path in carried}
    missing = tracked - names
    if missing:
        raise SystemExit('Refusing to install: the package is missing %s, which git tracks '
                         'beside the runtime.' % ', '.join(sorted(missing)))
    # An untracked file beside the runtime is installed with it, and one named after a standard
    # module (json.py) shadows it and stops review_flow.py from importing, guard and all.
    extra = names - tracked
    if extra:
        raise SystemExit('Refusing to install: %s beside the runtime is not tracked by git, and '
                         'would be installed with it. Remove it or track it.' % ', '.join(sorted(extra)))


def install(home, overlay):
    """Apply a prevalidated policy/settings merge with recoverable file backups."""
    home = home.resolve()
    settings_path, policy_path = home / 'settings.json', home / 'CLAUDE.md'
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    complete(payload())
    updated_policy = policy(policy_path.read_text() if policy_path.exists() else '')
    runtime = home / 'bymax-review'
    updated_settings = hook_settings(settings, runtime / 'review_push.py', home)
    # Prevalidated means every target resolves before the first write: a rejected overlay
    # must leave no backup directory behind, however many retries it takes to fix.
    targets = overlay_targets(home) if overlay else []
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup_dir = home / 'backups' / ('bymax-review-' + stamp)
    backup_dir.mkdir(parents=True, mode=0o700)
    paths = [settings_path, policy_path, runtime, home / 'hooks/code-review-clear.sh']
    for path in paths:
        backup(path, backup_dir, home)
    overlays(targets, home, backup_dir)
    runtime.mkdir(parents=True, exist_ok=True)
    # review_flow.start installs review_prepush.py from beside itself, so the hook
    # source must travel with the runtime or no repository ever gets the hook.
    for source in payload():
        shutil.copy2(source, runtime / source.name)
    settings_path.write_text(json.dumps(updated_settings, indent=2) + '\n')
    policy_path.write_text(updated_policy)
    legacy = home / 'hooks/code-review-clear.sh'
    if legacy.exists():
        legacy.write_text('#!/usr/bin/env bash\n# Review adapter: explicit evidence replaces assertion-only clearance.\n'
                          'echo "Use review_flow.py finish after both reports, triage and gates." >&2\nexit 2\n')
    print('Backups:', backup_dir)
    print('Installed bounded review policy and hook. Restart Claude to reload plugin content.')
    print('Per repository, once: run /bymax-quality:review-md to generate REVIEW.md and the '
          'AGENTS.md Code Review Rules. The PR reviewers read those files, and an installer '
          'cannot write them for a repository it has never seen.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude-home', type=Path, default=Path.home() / '.claude')
    parser.add_argument('--local-plugin-overlay', action='store_true',
                        help='Copy source into installed user plugin caches; official updates can replace it.')
    args = parser.parse_args()
    install(args.claude_home, args.local_plugin_overlay)
