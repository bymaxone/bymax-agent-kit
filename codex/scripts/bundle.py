#!/usr/bin/env python3
"""Build-layer bundler: ship unchanged Claude resources inside the Codex package."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'codex/plugins/bymax-codex'
DESTINATION = PACKAGE / 'references/upstream'


def shipped():
    """Every file under plugins/ that the repository actually ships.

    Asked of git rather than of the working tree, because the working tree also holds
    whatever a local run left behind. A .pytest_cache written by running the suite here
    became four canonical resources and four manifest entries that no clone has, so the
    bundle verified on the machine that produced it and was stale everywhere else.
    """
    # Bytes, not text: -z is asked for so a name is delimited by NUL and nothing else, and
    # universal-newline translation rewrites a CR inside a name before the split, dropping the
    # file it belongs to without a word.
    try:
        listing = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', 'plugins'],
                                 capture_output=True)
    except OSError as error:
        raise SystemExit('bundle.py asks git which files this repository ships, and git could '
                         f'not be run: {error}. Install git, or run the bundler from a checkout.')
    if listing.returncode != 0:
        raise SystemExit('bundle.py asks git which files this repository ships, and git could '
                         f'not answer in {ROOT}: {listing.stderr.decode(errors="replace").strip()}. '
                         'Run it from a checkout rather than from an exported tree.')
    names = [name for name in listing.stdout.split(b'\0') if name]
    # An empty answer is not an empty repository. git exits 0 and prints nothing whenever the
    # index holds no plugins/ entry while the directory is full — an unpacked copy inside
    # another repository, a re-inited checkout before its first add, a foreign GIT_DIR. Believing it
    # would delete every bundled resource and report success, so it stops here instead.
    if not names:
        raise SystemExit(f'git tracks no file under plugins/ in {ROOT}, so the canonical set '
                         'would be empty and bundling would delete every shipped resource. Run '
                         'the bundler from the checkout that tracks these files.')
    return {(ROOT / os.fsdecode(name)).resolve() for name in names}


def source_files():
    """Return runtime resources without registering Claude manifests or hooks."""
    tracked = shipped()
    for plugin in sorted((ROOT / 'plugins').iterdir()):
        for directory in ('commands', 'skills', 'agents', 'templates', 'scripts', 'hooks', 'references'):
            for path in sorted((plugin / directory).rglob('*')):
                if path.is_file() and path.resolve() in tracked:
                    yield path


def expected_files():
    """Map package-relative resource paths to canonical bytes."""
    files = {path.relative_to(ROOT / 'plugins'): path.read_bytes() for path in source_files()}
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
