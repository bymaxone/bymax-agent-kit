#!/usr/bin/env python3
"""Build-layer bundler: ship unchanged Claude resources inside the Codex package."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'codex/plugins/bymax-codex'
DESTINATION = PACKAGE / 'references/upstream'


BUNDLED = ('commands', 'skills', 'agents', 'templates', 'scripts', 'hooks', 'references')


def own_index():
    """Whether the index that would answer about ignores is this repository's own.

    `rev-parse --show-toplevel` names the working tree the answering index belongs to. For a
    clone, a linked worktree, a submodule and a shallow checkout that is this directory; for a
    copy unpacked inside another repository it is the enclosing one, whose patterns would apply
    to every resource here because it tracks none of them.
    """
    answer = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--show-toplevel'],
                            capture_output=True)
    if answer.returncode != 0:
        return False
    toplevel = Path(os.fsdecode(answer.stdout.strip()))
    return toplevel.resolve() == ROOT.resolve()


def ignored(candidates):
    """Which of these resources git is told to ignore.

    This is the whole of what git is asked. An earlier version asked git the opposite
    question — which files the repository ships — and that answer is wrong in more ways than
    it is right: git prints nothing when its index holds no plugins/ entry, prints one name
    when plugins/ is tracked as a symlink, and prints a subset when the index is partial or
    belongs to another repository. Each of those made the canonical set smaller, and a set
    that is too small does not fail: it deletes the mirror and reports success. Measured on
    this package while it worked that way — 111 files to 0, and 111 to 30.

    Asked this way round the failure is inverted: a bad answer makes the set too LARGE, which
    shows up as extra files in a diff somebody reads rather than as a silent deletion. What
    makes that true is not the direction of the question but the index behind it — check-ignore
    consults the index and never reports a TRACKED path as ignored, so no pattern can remove a
    resource the repository ships.

    That veto belongs to one index, and only the repository rooted here holds it. Where the
    index answering belongs to an enclosing repository, every resource is untracked to it and
    every one of its patterns applies: an outer .gitignore of `templates/` took this package
    from 111 files to 85 with exit 0 while that went unnoticed. So the answer is used only when
    it is about this tree, and otherwise nothing is left out — over-inclusion being the failure
    this mechanism is willing to have.
    """
    if not candidates or not own_index():
        return set()
    names = b'\0'.join(os.fsencode(str(path.relative_to(ROOT))) for path in candidates)
    try:
        answer = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '--stdin', '-z'],
                                input=names, capture_output=True)
    except OSError as error:  # kept: own_index() reports False rather than raising
        raise SystemExit('bundle.py asks git which resources to leave out of the package, and '
                         f'git could not be run: {error}. Install git, or run the bundler from a '
                         'checkout.')
    # check-ignore exits 1 when it matched nothing, which is an answer, not a failure.
    if answer.returncode > 1:
        raise SystemExit('bundle.py asks git which resources to leave out of the package, and git '
                         f'could not answer in {ROOT}: '
                         f'{answer.stderr.decode(errors="replace").strip()}. Run the bundler from a '
                         'checkout of this repository, with plugins/ a real directory.')
    # Bytes throughout: -z is asked for so a name is delimited by NUL and nothing else, and
    # universal-newline translation would rewrite a CR inside one before the split.
    return {ROOT / os.fsdecode(name) for name in answer.stdout.split(b'\0') if name}


def source_files():
    """Return runtime resources without registering Claude manifests or hooks."""
    if not shutil.which('git'):
        raise SystemExit('bundle.py asks git which resources to leave out of the package, and '
                         'git is not on PATH. Install git, or run the bundler from a checkout.')
    plugins = ROOT / 'plugins'
    if not plugins.is_dir():
        raise SystemExit(f'{plugins} is not a directory, so there is nothing to bundle. Run the '
                         'bundler from a checkout of this repository.')
    candidates = [path
                  for plugin in sorted(plugins.iterdir())
                  for directory in BUNDLED
                  for path in sorted((plugin / directory).rglob('*')) if path.is_file()]
    skip = ignored(candidates)
    return [path for path in candidates if path not in skip]


def expected_files():
    """Map package-relative resource paths to canonical bytes.

    The one refusal left guards the value that drives synchronize()'s deletions. It is the
    only guard this mechanism needs: nothing above can make the set smaller than the disk, so
    an empty set means the resources are not there to read — a checkout missing its
    directories, or plugins/ that is not a directory at all.
    """
    files = {path.relative_to(ROOT / 'plugins'): path.read_bytes() for path in source_files()}
    if not files:
        raise SystemExit(f'no resource was found under {ROOT / "plugins"}, so the canonical set is '
                         'empty and bundling would delete every shipped file. A package is never '
                         'empty: check that the resource directories are present and that plugins/ '
                         'holds them.')
    return files


def synchronize(check):
    """Copy exact resources, or fail if the distributable snapshot has drifted."""
    expected = expected_files()
    license_path = PACKAGE / 'LICENSE'
    license_bytes = (ROOT / 'LICENSE').read_bytes()
    if check and (not license_path.is_file() or license_path.read_bytes() != license_bytes):
        raise SystemExit('Codex license copy is stale; run the bundler')
    if not check:
        license_path.write_bytes(license_bytes)
    actual = {p.relative_to(DESTINATION) for p in DESTINATION.rglob('*') if p.is_file()}
    stale = actual - expected.keys()
    changed = [p for p, data in expected.items()
               if not (DESTINATION / p).is_file() or (DESTINATION / p).read_bytes() != data]
    manifest = {str(p): hashlib.sha256(data).hexdigest() for p, data in expected.items()}
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    index = PACKAGE / 'references/upstream-sha256.json'
    index_changed = not index.is_file() or index.read_bytes() != encoded
    if check and (stale or changed or index_changed):
        raise SystemExit('Codex bundle is stale; run python3 codex/scripts/bundle.py')
    if not check:
        for path in stale:
            (DESTINATION / path).unlink()
        for path, data in expected.items():
            target = DESTINATION / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        index.write_bytes(encoded)
    print(f'Codex bundle verified: {len(expected)} canonical resources')


def section(source, start, stop):
    """Cut a required heading range, failing loudly when a delimiter is renamed.

    str.split returns the whole string when its separator is absent, so an outdated
    delimiter would silently ship the excluded section instead of dropping it.
    """
    for delimiter in (start, stop):
        if delimiter not in source:
            raise SystemExit(f'code-review.md no longer contains {delimiter!r}; update the bundler')
    return source.split(start, 1)[1].split(stop, 1)[0]


def checklist(check):
    """Extract the shared review rules without Claude's launch/report machinery."""
    source = (ROOT / 'plugins/bymax-quality/commands/code-review.md').read_text()
    body = section(source, '## Step 2 — Mechanical gate (deterministic)',
                   '## Step 5.5 — Complete the bounded campaign')
    text = ('# Shared Bymax review checklist\n\n'
            'Generated from the Claude command; do not edit this copy. The Codex\n'
            'code-review entrypoint overrides scope acquisition, mechanical-hit\n'
            'classification, tool calls and reporting. Read these rules as reference.\n\n'
            '## Step 2 — Mechanical gate (deterministic)' + body)
    target = PACKAGE / 'references/review-checklist.md'
    if check and (not target.is_file() or target.read_text() != text):
        raise SystemExit('Codex review checklist is stale; run the bundler')
    if not check:
        target.write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    check = parser.parse_args().check
    synchronize(check)
    checklist(check)
