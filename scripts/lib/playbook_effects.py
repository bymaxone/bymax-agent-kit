"""Library layer: which vendored playbooks prescribe a command that writes to another system.

The approval rule itself is general: the security-playbooks index asks before any command that
changes or publishes outside the project, whether the notes list it or not, because no pattern
recognises every spelling of such a command. This module is the tripwire under that rule. It
reads each playbook's procedure text (`SKILL.md` and `references/*.md`, where the commands an
agent is told to run live) for the common spellings, so that a refresh bringing a new one in
fails the vendor test until the notes describe it.
"""
import re
from pathlib import Path

# Common spellings of a command that changes state outside the project. An HTTP write is curl
# with a write method, or with a body option that makes it a POST. A GitHub API write is
# gh api with a write method, or with a field or input that makes it a POST. Also a mutating
# kubectl verb, helm or terraform change, a package or image publish, a signature, an
# attestation, or a forced push. Reads such as `cosign verify`, `kubectl get` and a plain
# `curl URL` do not match.
REMOTE_WRITE = re.compile(
    r'\bcurl\b[^|\n]*(?:(?:-X|--request)[ =]?(?:POST|PUT|PATCH|DELETE)\b'
    r'|\s(?:-d|-F|-T|--data(?:-[a-z]+)?|--form|--json|--upload-file)(?=[\s=]))'
    r'|\bgh api\b[^|\n]*(?:(?:--method|-X)[ =]?(?:POST|PUT|PATCH|DELETE)\b'
    r'|\s(?:-f|-F|--field|--raw-field|--input)(?=[\s=]))'
    r'|\bkubectl (?:apply|delete|create|patch|replace|edit|scale|rollout|set|label|annotate'
    r'|debug|exec|run|cp|taint|drain|cordon)\b'
    r'|\bhelm (?:install|upgrade|uninstall|rollback)\b'
    r'|\bterraform (?:apply|destroy|import)\b'
    r'|\bdocker (?:push|trust sign)\b|\bnpm publish\b'
    r'|\bcosign (?:sign|attest)\b'
    r'|\bgit push\b[^\n]*(?:--force|\s-f\b)')


def commands(text: str):
    """Each logical line with the number of its first physical line.

    A shell command continued with a trailing backslash is one command, so its flags on later
    lines are read together with the program that takes them.
    """
    start, parts = None, []
    for number, line in enumerate(text.splitlines(), start=1):
        start = number if start is None else start
        if line.rstrip().endswith('\\'):
            parts.append(line.rstrip()[:-1])
            continue
        yield start, ' '.join([*parts, line])
        start, parts = None, []
    if parts:
        yield start, ' '.join(parts)


def effect(command: str) -> str:
    """The word a notes row must carry for this remote write: the host an HTTP write goes to,
    or the command or flag that makes the change."""
    match = REMOTE_WRITE.search(command)
    if match.group(0).startswith('curl'):
        host = re.search(r'https?://([^/"\'\s]+)', command)
        return host.group(1) if host else 'curl'
    if match.group(0).startswith('git push'):
        return '--force'
    return ' '.join(match.group(0).split()[:2])


def remote_writes(playbooks: Path) -> dict:
    """Each playbook folder whose procedure prescribes a remote write: `{effect: [file:line]}`."""
    found = {}
    for folder in sorted(path for path in playbooks.iterdir() if path.is_dir()):
        texts = [folder / 'SKILL.md', *sorted((folder / 'references').glob('*.md'))]
        for text in (path for path in texts if path.is_file()):
            for number, command in commands(text.read_text()):
                if REMOTE_WRITE.search(command):
                    hit = f'{text.relative_to(folder).as_posix()}:{number}'
                    found.setdefault(folder.name, {}).setdefault(effect(command), []).append(hit)
    return found


def approval_rows(notes: Path) -> dict:
    """Each playbook's rows in the notes section listing what needs the user's approval."""
    text = notes.read_text()
    start = text.index('## Ask before running')
    end = text.find('\n## ', start + 1)
    section = text[start:] if end == -1 else text[start:end]
    rows = {}
    for line in section.splitlines():
        if line.startswith('| `'):
            cells = line.split('|')
            for name in re.findall(r'`([a-z0-9-]+)`', cells[1]):
                rows[name] = rows.get(name, '') + line
    return rows


def unlisted(playbooks: Path, notes: Path) -> dict:
    """Remote writes whose playbook has no approval row naming that effect."""
    rows = approval_rows(notes)
    missing = {}
    for name, effects in remote_writes(playbooks).items():
        for word, hits in effects.items():
            if word not in rows.get(name, ''):
                missing.setdefault(name, {})[word] = hits
    return missing
