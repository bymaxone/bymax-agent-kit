#!/usr/bin/env python3
"""Installation layer: register and verify only the repository's Codex package."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = ROOT / 'codex'
PACKAGE = MARKETPLACE / 'plugins/bymax-codex'
SELECTOR = 'bymax-codex@bymax-codex'


def call(*arguments):
    """Read a CLI JSON response, preserving command failures as installation failures."""
    result = subprocess.run(['codex', *arguments, '--json'], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or 'Codex command failed')
    return json.loads(result.stdout)


def verify_source():
    """Require the checked-in resource snapshot to match its source repository."""
    subprocess.run(['python3', str(MARKETPLACE / 'scripts/bundle.py'), '--check'], check=True)
    return json.loads((PACKAGE / '.codex-plugin/plugin.json').read_text())


def verify_marketplace():
    """Reject a same-name marketplace that belongs to a different checkout."""
    listing = call('plugin', 'marketplace', 'list')
    for entry in listing['marketplaces']:
        if entry['name'] == 'bymax-codex' and Path(entry['root']).resolve() != MARKETPLACE.resolve():
            raise ValueError('Marketplace bymax-codex already points elsewhere: ' + entry['root']
                             + '. Use that checkout or explicitly remove/re-register the marketplace.')


def verify_installed(version):
    """Confirm installed/enabled state and the intended local source through a fresh read."""
    listing = call('plugin', 'list', '--marketplace', 'bymax-codex')
    for entry in listing['installed']:
        if entry['pluginId'] != SELECTOR:
            continue
        if not entry.get('installed') or not entry.get('enabled') or entry.get('version') != version:
            raise ValueError('Bymax Codex is not installed and enabled at version ' + version)
        source = entry.get('source', {})
        if source.get('source') != 'local' or Path(source.get('path', '')).resolve() != PACKAGE.resolve():
            raise ValueError('Installed plugin does not point to this package')
        return
    raise ValueError('Bymax Codex is absent from the installed plugin list')


def verify_cache(path):
    """Check the actual installed cache is self-contained and identical to this release."""
    installed = Path(path)
    expected = {p.relative_to(PACKAGE): p for p in PACKAGE.rglob('*')
                if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    for relative, source in expected.items():
        target = installed / relative
        if not target.is_file() or source.read_bytes() != target.read_bytes():
            raise ValueError(f'Installed cache differs at {relative}; release a new Codex plugin version and reinstall')
    print(f'Installed cache verified: {len(expected)} files at {installed}')


def main():
    """Install, inspect, or preview without modifying Claude or unrelated Codex settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    manifest = verify_source()
    if args.dry_run:
        print(f'Would register Codex marketplace: {MARKETPLACE}')
        print(f'Would install {SELECTOR} version {manifest["version"]}')
        print('Would verify installed/enabled state and cached package contents; no Claude writes.')
        return
    if not shutil.which('codex'):
        raise ValueError('Codex CLI is required: https://developers.openai.com/codex/cli/')
    if not shutil.which('git'):
        raise ValueError('Git is required for code review; install it before using this package')
    verify_marketplace()
    if not args.check:
        result = call('plugin', 'marketplace', 'add', str(MARKETPLACE))
        if result['marketplaceName'] != 'bymax-codex':
            raise ValueError('Codex registered an unexpected marketplace')
        result = call('plugin', 'add', SELECTOR)
        if result['pluginId'] != SELECTOR or result['version'] != manifest['version']:
            raise ValueError('Codex installed an unexpected plugin/version')
        verify_cache(result['installedPath'])
    verify_installed(manifest['version'])
    print('Verified: ' + SELECTOR + ' installed and enabled at ' + manifest['version'])
    if args.check:
        print('Check mode verifies registration/state; run the installer to verify cached bytes too.')
    else:
        print('Start a new Codex task and select bymax-codex:bymax-code-review to verify skill discovery.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Codex installation failed: {error}') from error
