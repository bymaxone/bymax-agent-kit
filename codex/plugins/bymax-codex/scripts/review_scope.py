#!/usr/bin/env python3
"""Review infrastructure: capture a read-only, reproducible Git review scope as JSON."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


def git(*args, allow_failure=False):
    """Run Git without shell interpolation, external diffs, or optional index writes."""
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(['git', *args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=environment, input=b'', check=False)
    if result.returncode and not allow_failure:
        raise ValueError(result.stderr.decode(errors='replace').strip())
    return result.stdout if result.returncode == 0 else None


def commit(ref):
    """Resolve a nonempty revision to an immutable commit, rejecting option injection."""
    if not ref or ref.startswith('-'):
        raise ValueError('A nonempty, non-option commit ref is required')
    return git('rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()


def default_base():
    """Resolve an existing upstream or remote default without guessing branch names."""
    for ref in ('@{upstream}', 'refs/remotes/origin/HEAD'):
        value = git('rev-parse', '--verify', ref + '^{commit}', allow_failure=True)
        if value:
            return value.decode().strip()
    raise ValueError('No upstream/default comparison base; pass --base explicitly')


def resolve(args):
    """Select working changes first, otherwise a pinned committed comparison."""
    head = git('rev-parse', '--verify', 'HEAD', allow_failure=True)
    head = head.decode().strip() if head else None
    status = git('status', '--porcelain=v1', '-z', '--untracked-files=all')
    mode = args.mode
    if mode == 'auto':
        mode = 'uncommitted' if status or head is None else 'branch'
    if mode == 'uncommitted':
        if git('ls-files', '--unmerged', '-z'):
            raise ValueError('Unmerged index entries; resolve conflicts before working-tree review')
        base = head or git('hash-object', '-t', 'tree', '--stdin').decode().strip()
        return mode, base, None, head
    if mode == 'commit':
        target = commit(args.head)
        parents = git('rev-list', '--parents', '-n', '1', target).decode().split()
        base = parents[1] if len(parents) > 1 else git('hash-object', '-t', 'tree', '--stdin').decode().strip()
        return mode, base, target, head
    base, target = commit(args.base) if args.base else default_base(), commit(args.head)
    if mode == 'branch':
        base = git('merge-base', base, target).decode().strip()
    return mode, base, target, head


def untracked_files(paths):
    """Capture new files without staging them or following symlinks outside the tree."""
    raw = git('ls-files', '--others', '--exclude-standard', '-z', '--', *paths)
    entries = []
    for value in raw.split(b'\0'):
        if not value:
            continue
        path = Path(os.fsdecode(value))
        data = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
        binary = b'\0' in data
        entries.append({'path': str(path), 'symlink': path.is_symlink(), 'binary': binary,
                        'sha256': hashlib.sha256(data).hexdigest(),
                        'content': None if binary else data.decode('utf-8', errors='replace')})
    return entries


def changed_files(names, target, base, paths):
    """Include index-only changes even when the worktree equals HEAD."""
    options = ['--no-ext-diff', '--no-textconv', '--no-renames', '--ignore-submodules=none']
    if target is None:
        names += git('diff', *options, '--cached', '--name-only', '-z', base, '--', *paths)
        names += git('diff', *options, '--name-only', '-z', '--', *paths)
    return sorted({os.fsdecode(p) for p in names.split(b'\0') if p})


def capture(args):
    """Return exact diff bytes and new-file evidence with a content fingerprint."""
    root = git('rev-parse', '--show-toplevel').decode().strip()
    os.chdir(root)
    paths = args.path or []
    if any(not value for value in paths):
        raise ValueError('--path cannot be empty')
    if any(Path(p).is_absolute() or '..' in Path(p).parts or p.startswith(':') for p in paths):
        raise ValueError('--path must be a literal repository-relative path')
    paths = [f':(literal){p}' for p in paths]
    mode, base, target, head = resolve(args)
    refs = [base, target] if target else [base]
    options = ['--no-ext-diff', '--no-textconv', '--no-renames', '--ignore-submodules=none', '--binary']
    diff = git('diff', *options, *refs, '--', *paths)
    added = git('diff', *options, '--output-indicator-new=>', '-U0', *refs, '--', *paths)
    names = git('diff', *options, '--name-only', '-z', *refs, '--', *paths)
    new = untracked_files(paths) if mode == 'uncommitted' else []
    staged = git('diff', *options, '--cached', base, '--', *paths) if target is None else b''
    unstaged = git('diff', *options, '--', *paths) if target is None else b''
    raw_digest = hashlib.sha256(diff + b'\0' + staged + b'\0' + unstaged).hexdigest()
    payload = {'raw_diff_sha256': raw_digest, 'mode': mode, 'base': base, 'head': target, 'checkout_head': head,
               'staged_diff': staged.decode(errors='replace'),
               'unstaged_diff': unstaged.decode(errors='replace'),
               'paths': args.path or [], 'diff': diff.decode(errors='replace'),
               'added_lines': [line[1:] for line in added.decode(errors='replace').splitlines()
                               if line.startswith('>')],
               'changed_files': changed_files(names, target, base, paths),
               'untracked': new}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return dict(payload, fingerprint=fingerprint, repository=root)


def arguments():
    """Parse explicit scope options; no positional argument is interpreted heuristically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['auto', 'uncommitted', 'branch', 'range', 'commit'], default='auto')
    parser.add_argument('--base')
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--path', action='append', help='Literal path relative to repository root')
    args = parser.parse_args()
    if args.base is not None and not args.base:
        parser.error('--base cannot be empty')
    if args.mode in ('auto', 'uncommitted') and (args.base or args.head != 'HEAD'):
        parser.error('--base/--head require --mode branch, range, or commit')
    if args.mode == 'range' and not args.base:
        parser.error('--mode range requires --base')
    if args.mode == 'commit' and args.base:
        parser.error('--mode commit does not accept --base')
    return args


def main():
    """Print evidence on success and fail closed on unresolved or unreadable scope."""
    try:
        print(json.dumps(capture(arguments()), indent=2, ensure_ascii=True))
    except (ValueError, OSError) as error:
        raise SystemExit(f'Review scope unavailable: {error}') from error


if __name__ == '__main__':
    main()
