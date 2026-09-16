# Attribution — ui-ux-pro-max

The contents of this folder are vendored from the **ui-ux-pro-max** Claude Code skill:

- **Project**: ui-ux-pro-max-skill
- **Author**: nextlevelbuilder
- **Repository**: <https://github.com/nextlevelbuilder/ui-ux-pro-max-skill>
- **Website**: <https://ui-ux-pro-max-skill.nextlevelbuilder.io/>
- **License**: MIT (see [`LICENSE`](./LICENSE) — copy of upstream license preserved)
- **Version vendored**: **v2.11.0** — snapshot taken on 2026-07-25

> This folder exists for the author's machine-restore flow. It is a point-in-time copy,
> so it drifts as upstream ships. To get the maintainer's latest, install from upstream
> (below) rather than copying from here.

## Why this is here

It's bundled in this repo as part of the author's **personal backup** — it's symlinked back into `~/.claude/skills/ui-ux-pro-max/` by [`scripts/install.sh`](../../scripts/install.sh) when restoring on a new Mac.

It is **NOT** listed in [`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json) and **cannot** be installed via `/plugin install` from this repo. Anyone who wants this skill should install it directly from the upstream maintainer:

```bash
claude plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill
claude plugin install ui-ux-pro-max@ui-ux-pro-max-skill
```

The suffix matters: the marketplace is named `ui-ux-pro-max-skill` (after the repo),
while the plugin inside it is `ui-ux-pro-max`. Installing `@ui-ux-pro-max` fails.

(Or follow the upstream README for the latest install command.)

## What this skill does

Design intelligence for Claude Code. Bundles:

- 84 styles (glassmorphism, claymorphism, brutalism, neumorphism, bento grid, etc.)
- 192 color palettes
- 74 font pairings
- 25 chart types
- 99 UX guidelines
- 192 product types
- 16 GSAP motion presets and 104 icon entries
- 22 stacks (React, Next.js, Astro, Vue, Nuxt.js, Nuxt UI, Svelte, SwiftUI, React Native, Flutter, Jetpack Compose, Tailwind/HTML, shadcn/ui, Angular, Laravel, JavaFX, WPF, WinUI, Avalonia, Uno Platform, UWP, Three.js)

Counts describe this vendored snapshot — verified against the CSVs in `data/` with a
CSV-aware parser (fields contain embedded newlines, so `wc -l` undercounts).

The skill auto-activates on UI/frontend tasks and recommends a complete design system based on product type and requirements.

## How to update from upstream

Run from the repo root. Note the `ATTRIBUTION.md` save/restore — this file lives
inside the folder being replaced, so a bare `rm -rf` would delete it.

```bash
# Clone fresh upstream
git clone --depth 1 https://github.com/nextlevelbuilder/ui-ux-pro-max-skill /tmp/uiux

# Preserve this attribution file before wiping the folder
cp vendor/ui-ux-pro-max/ATTRIBUTION.md /tmp/ATTRIBUTION.keep.md

# Replace the skill content (note the trailing /. — copies dotfiles too)
rm -rf vendor/ui-ux-pro-max
mkdir -p vendor/ui-ux-pro-max
cp -R /tmp/uiux/.claude/skills/ui-ux-pro-max/. vendor/ui-ux-pro-max/

# Update LICENSE if upstream changed it, and restore attribution
cp /tmp/uiux/LICENSE vendor/ui-ux-pro-max/LICENSE
cp /tmp/ATTRIBUTION.keep.md vendor/ui-ux-pro-max/ATTRIBUTION.md

# Verify the copy, then refresh the version + counts above
cd vendor/ui-ux-pro-max
python3 scripts/validate_data.py
python3 -m unittest discover -s scripts/tests -q
```

---

If you are the author of ui-ux-pro-max and prefer this content not be vendored here, please [open an issue](https://github.com/bymaxone/bymax-agent-kit/issues) — we'll remove it promptly.
