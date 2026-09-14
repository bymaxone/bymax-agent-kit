#!/usr/bin/env python3
"""Validation layer: check Codex entrypoints, manifests and portable resource links."""

import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'codex/plugins/bymax-codex'


def validate_manifests():
    """Check package identity, version and the marketplace's local source resolution."""
    market = json.loads((ROOT / 'codex/.agents/plugins/marketplace.json').read_text())
    manifest = json.loads((PACKAGE / '.codex-plugin/plugin.json').read_text())
    assert market['name'] == manifest['name'] == 'bymax-codex'
    assert re.fullmatch(r'\d+\.\d+\.\d+(?:\+[A-Za-z0-9.-]+)?', manifest['version'])
    assert manifest['skills'] == './skills/'
    assert not {'hooks', 'mcpServers', 'apps'} & manifest.keys()
    assert len(market['plugins']) == 1
    entry = market['plugins'][0]
    assert entry['name'] == manifest['name']
    assert entry['source'] == {'source': 'local', 'path': './plugins/bymax-codex'}
    assert entry['policy'] == {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'}
    assert entry['category'] == 'Productivity'
    assert not (PACKAGE / 'hooks').exists(), 'Claude hooks must remain inert references'


def validate_links(path):
    """Require native relative Markdown links to resolve inside the distributable."""
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if '://' in target or target.startswith('#'):
            continue
        resolved = (path.parent / target.split('#')[0]).resolve()
        assert resolved.is_relative_to(PACKAGE.resolve()), f'External package link: {path}: {target}'
        assert resolved.exists(), f'Missing package link: {path}: {target}'


def validate_skills():
    """Match every source command/skill to one valid, discoverable Codex entrypoint."""
    catalog = json.loads((PACKAGE / 'references/catalog.json').read_text())
    paths = sorted((PACKAGE / 'skills').glob('*/SKILL.md'))
    assert {p.parent.name for p in paths} == set(catalog)
    sources = {str(p.relative_to(ROOT / 'plugins')) for p in (ROOT / 'plugins').glob('*/commands/*.md')}
    sources |= {str(p.relative_to(ROOT / 'plugins')) for p in (ROOT / 'plugins').glob('*/skills/*/SKILL.md')}
    assert set(catalog.values()) == sources, 'Codex catalog must account for every source entrypoint'
    for path in paths:
        text = path.read_text()
        assert text.startswith('---\n')
        data = yaml.safe_load(text.split('---', 2)[1])
        assert data['name'] == path.parent.name
        assert re.fullmatch('[a-z0-9-]{1,64}', data['name'])
        assert isinstance(data['description'], str) and data['description'].strip()
        assert set(data) <= {'name', 'description', 'metadata'}
        assert '[TODO:' not in text
        validate_links(path)
    for path in (PACKAGE / 'references').glob('*.md'):
        validate_links(path)
    print(f'Codex skills verified: {len(paths)} entrypoints with portable links')


def main():
    """Run build-drift and native contract validation; missing dependencies fail closed."""
    subprocess.run(['python3', str(ROOT / 'codex/scripts/bundle.py'), '--check'], check=True)
    validate_manifests()
    validate_skills()


if __name__ == '__main__':
    main()
