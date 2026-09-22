# Codex package maintenance

This directory is a standalone **local Codex marketplace root**. Installation
instructions are in [../CODEX.md](../CODEX.md). The Claude marketplace and all its
existing runtime files stay in their original locations.

```text
codex/
  .agents/plugins/marketplace.json
  plugins/bymax-codex/
    .codex-plugin/plugin.json
    skills/bymax-*/SKILL.md
    scripts/review_scope.py
    references/runtime.md
    references/catalog.json
    references/upstream/              # exact bundled Claude resources
    references/upstream-sha256.json
    references/review-checklist.md    # extracted shared review sections
  scripts/                           # packaging, installation and validation
  tests/                             # isolated behavioral checks
```

## Sources and ownership

- `../plugins/` remains the canonical source for existing Bymax procedures,
  references, templates, roles and scripts. Nothing is moved out of that tree.
- Native Codex entrypoints and `references/runtime.md` define how those rules
  execute here. Treat source-specific tool names and frontmatter as reference,
  never as automatically installed tools or permissions.
- `scripts/bundle.py` copies runtime resources byte-for-byte and extracts the
  shared review checklist. CI compares the bundle with the canonical files so
  edits cannot silently drift. The package includes its license.
- The catalog maps every source command and skill to one native entrypoint.
  Web verify and workflow verify have distinct names. All ten source agent roles
  are available as bundled references; they are not registered Claude agents.
- No root-level Codex hooks or MCP configuration is shipped. Nested upstream
  hooks are inert reference material. Do not add a guarantee without a host
  integration and a behavioral test proving it.

## Making changes

For shared rule changes, edit the canonical source, honor that Claude plugin's
version/changelog rules, run the bundler, and bump the Codex manifest version.
For Codex-only changes, edit native files and bump only the Codex package version;
the Claude plugin and marketplace versions remain unchanged. Add the release note
to the repository changelog. Never hand-edit the bundled resources or hash index.

Before release, run both validation scripts from the root. The native validator
requires Python 3.10+ and PyYAML. Installation and runtime scope capture use only
the standard library, Git, and the supported Codex CLI. The installer uses
`plugin add`, verified against CLI help, rather than `plugin install`.

The integration test uses a temporary CODEX_HOME exclusively for the test process;
it does not replace the user's actual settings or install anything in their
normal profile. It checks installation, idempotence, enabled state, all 28 skills through the real app-server loader, and the cached
review helper from a different repository. To require this test locally, use:

```bash
BYMAX_REQUIRE_CODEX_TEST=1 ./scripts/validate-codex.sh
```

A model-driven review of realistic fixtures is still useful before a release:
mechanical validation proves packaging and Git semantics, not that every host's
agent, browser or scheduler adapter has been exercised.
