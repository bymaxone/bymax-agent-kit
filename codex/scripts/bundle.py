#!/usr/bin/env python3
"""Build-layer bundler: ship unchanged Claude resources inside the Codex package."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'codex/plugins/bymax-codex'
DESTINATION = PACKAGE / 'references/upstream'


def source_files():
    """Return runtime resources without registering Claude manifests or hooks."""
    for plugin in sorted((ROOT / 'plugins').iterdir()):
        for directory in ('commands', 'skills', 'agents', 'templates', 'scripts', 'hooks', 'references'):
            for path in sorted((plugin / directory).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:
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
