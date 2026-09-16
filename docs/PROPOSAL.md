# 🗂️ Original design proposal — bymax-claude-code

> Saved on 2026-04-25 from the conversation that led to this repo. Kept here as a record of
> the design decisions and the rationale for the layout you see today.
>
> **Historical document.** The project is now **Bymax Agent Kit** (`bymaxone/bymax-agent-kit`)
> and ships a second package for Codex alongside the Claude Code marketplace. The old name and
> the Claude-only plugin list below are preserved as written; the current layout is in the
> [README](../README.md).

---

## What we wanted

1. **Personal backup** — clone repo on a new Mac, run install script, `~/.claude/` restored.
2. **Public marketplace** — anyone can `claude plugin install` curated subsets.
3. **MIT-respectful** — third-party content (ECC, ui-ux-pro-max) preserved with attribution but **not** redistributed via the marketplace itself.
4. **Professional polish** — README, badges, license, contributing, security policy, GitHub workflows. Ready to be public.

## Why this layout

```
bymax-claude-code/
├── .claude-plugin/marketplace.json   ← the marketplace contract
├── plugins/                          ← what /plugin install can fetch
│   ├── bymax-workflow/
│   ├── bymax-quality/
│   ├── bymax-bootstrap/
│   └── bymax-all/
├── templates/                        ← project starters (CLAUDE/AGENTS/README)
├── vendor/                           ← third-party MIT skills (backup, with attribution)
├── personal/                         ← author-only stuff (backup, not for marketplace)
├── scripts/                          ← install + validate
└── docs/                             ← like this file
```

### Why split into 3 plugins (workflow / quality / bootstrap) + a meta?

Anthropic's own `claude-plugins-official` does the same — one plugin per concern. Lets users pick what they want without forcing them to take everything.

- `bymax-workflow` — planning + execution. Heavy on slash commands.
- `bymax-quality` — review + TDD + agents + hooks. Where the gates live.
- `bymax-bootstrap` — project scaffolding. Heavy on templates.
- `bymax-all` — meta, depends on the three above. Recommended starting point.

### Why `vendor/` is in the repo but NOT in the marketplace

The author uses ECC skills (api-design, backend-patterns, etc.) and ui-ux-pro-max personally. To restore on a new Mac, those need to be in the repo somewhere. But:

- They're **not the author's IP** — bundling them in `plugins/` and exposing via `/plugin install` would be re-publishing third-party work.
- MIT permits redistribution **with attribution and license preservation**. So they sit in `vendor/` with `LICENSE` + `ATTRIBUTION.md` per subfolder, visible but not installable through the marketplace.

The install script symlinks them into `~/.claude/skills/` for the author. Anyone else cloning the repo sees them as documentation pointing to upstream.

### Why `personal/` is in the repo

Same reason: backup. Things like `/sim` (Expo simulator helper) or `prettier-format.sh` are too project-specific to put in the marketplace, but the author wants them restored after a wipe. They live in `personal/` with a `README.md` explaining they're not for general use.

### Why `templates/` are at the repo root, not just inside `bymax-bootstrap`

The user explicitly asked for `CLAUDE.md`, `AGENTS.md`, and `README.md` templates as **first-class artifacts** — not buried inside a plugin's templates folder. So they live at the repo root in `templates/` where they're easy to find and edit. The `bymax-bootstrap` plugin's own templates folder also has copies of the workflow doc templates (`spec`, `roadmap`, `phase-tasks`) that `/spec`, `/roadmap`, `/phase-tasks` use.

## Original recommendations table

Saved for posterity. These are the items we discussed before building this repo:

| Tier | Item | Status |
| --- | --- | --- |
| 1 | Audit & disable unused plugins (token savings) | User decides per-machine |
| 1 | Lower `effortLevel` from `high` to `medium` | User decides per-machine |
| 2 | Trim `/tdd` worked example (~3K → ~250 lines) | ✅ Done |
| 2 | `/task` references `/standards` sections instead of loading whole skill | ✅ Done |
| 3 | Memory consolidation periodically | User decides (1×/month suggested) |
| 3 | Tighten `console-log-scan.sh` early-exits | ✅ Done |

## Future improvements

- GitHub Action to auto-validate `marketplace.json` and every `plugin.json` on PR (already drafted in `.github/workflows/validate.yml`).
- Auto-publish version bumps via release-please or similar.
- Add stack templates for Vue, Svelte, SolidStart, Astro, Remix.
- A `/release` skill that bumps semver, updates CHANGELOG, tags.
- A `/triage` skill for automated issue triage workflow.
- An animated demo (asciinema cast) embedded in the main README.
