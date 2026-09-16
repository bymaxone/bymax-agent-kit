# 📦 Vendor

This folder bundles **third-party Claude Code skills** the author uses personally. Both are MIT-licensed and the original `LICENSE` and an `ATTRIBUTION.md` are preserved in each subfolder.

These skills are **NOT** redistributed via the marketplace (they're not listed in `marketplace.json` and `/plugin install` cannot fetch them from here). They live here for two reasons:

1. **Personal backup** — when the author restores `~/.claude/` on a new Mac via [`scripts/install.sh`](../scripts/install.sh), these get symlinked back too.
2. **Discoverability** — readers of this repo can see the original sources and install them properly from the upstream maintainers.

---

## What's in here

### [`ecc-skills/`](./ecc-skills/) — Everything Claude Code

A subset of skills from [Everything Claude Code (ECC)](https://github.com/affaan-m/everything-claude-code) by **Affaan Mustafa**. ECC is an open-source agent harness with **200K+ stars** and 119 skills.

The seven skills bundled here are domain-knowledge skills for backend, frontend, API design, database migrations, postgres patterns, security review, and coding standards.

→ For the full collection, install ECC at <https://github.com/affaan-m/everything-claude-code>.

Audited against upstream on 2026-07-25: all seven have drifted, but only cosmetically —
upstream renested `origin: ECC` under a `metadata:` key and swapped ✅/❌ markers for
`PASS:`/`FAIL:` text (which reads worse in places, e.g. `// PASS: GOOD: …`). No content
change, so this snapshot is deliberately **not** refreshed.

### [`ui-ux-pro-max/`](./ui-ux-pro-max/) — UI/UX Design Intelligence

A complete UI/UX design intelligence skill from [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) by **nextlevelbuilder**.

Vendored at **v2.11.0**. Bundles 84 styles, 192 color palettes, 74 font pairings, 99 UX guidelines, 192 product types, and 25 chart types across 22 stacks (React, Next.js, Astro, Vue, Nuxt.js, Nuxt UI, Svelte, SwiftUI, React Native, Flutter, Jetpack Compose, Tailwind/HTML, shadcn/ui, Angular, Laravel, JavaFX, WPF, WinUI, Avalonia, Uno Platform, UWP, Three.js).

→ For updates and the canonical version, install at <https://github.com/nextlevelbuilder/ui-ux-pro-max-skill>.

---

## Design skills — fetched from upstream, **not** vendored

A set of third-party **design** skills the author uses are deliberately **not** copied into this folder. Instead, [`scripts/install.sh`](../scripts/install.sh) fetches them from their original repos via the [`skills`](https://www.npmjs.com/package/skills) CLI (`npx skills add … --global`). Two reasons: licensing (Impeccable is Apache-2.0; the Emil skill ships no license file) and freshness (you always get the maintainer's latest version).

| Skill | Author | License | Source |
| ----- | ------ | ------- | ------ |
| [Emil Design Engineering](https://github.com/emilkowalski/skill) | Emil Kowalski | _no license file_ | `emilkowalski/skill` |
| [Impeccable](https://github.com/pbakaus/impeccable) | Paul Bakaus | Apache-2.0 | `pbakaus/impeccable` |
| [Taste-Skill](https://github.com/Leonxlnx/taste-skill) (subset) | Leonxlnx | MIT | `Leonxlnx/taste-skill` |

Install them yourself (or let `install.sh` do it):

```bash
npx skills add emilkowalski/skill --global --skill emil-design-eng --yes
npx skills add pbakaus/impeccable --global --skill impeccable --yes
npx skills add Leonxlnx/taste-skill --global \
  --skill design-taste-frontend \
  --skill redesign-existing-projects \
  --skill minimalist-ui \
  --skill industrial-brutalist-ui \
  --skill high-end-visual-design --yes
```

> **`--skill` takes one name per flag.** A comma-separated list is read as a single
> skill name, so the CLI finds nothing and exits 1 with `No matching skills found`.
>
> The CLI also prints `Failed to install → PromptScript does not support global skill
> installation` on every run. That is a *different* agent target failing, not Claude
> Code — the same output says `symlinked: Claude Code` on success, and the exit code
> stays 0. Verify the real result with `ls ~/.claude/skills/<name>/SKILL.md`.

Skip the automatic fetch with `./scripts/install.sh --no-design-skills`.

---

## License compliance

Both vendored skills are MIT-licensed. Per MIT terms, redistribution is permitted as long as:

- ✅ The original copyright notice is preserved (see `LICENSE` file in each subfolder).
- ✅ Attribution to the original author is given (see `ATTRIBUTION.md` in each subfolder).

If you are the author of either project and prefer not to be vendored here, please [open an issue](https://github.com/bymaxone/bymax-agent-kit/issues) and we'll remove your content.

---

## How to install these (officially)

If you want these skills, **install from the original sources** (not from this repo). That way you get updates automatically:

```bash
# Everything Claude Code
git clone https://github.com/affaan-m/everything-claude-code ~/dotfiles-ecc
# follow ECC's install instructions

# ui-ux-pro-max
claude plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill
claude plugin install ui-ux-pro-max@ui-ux-pro-max-skill
# (or follow the upstream README)
```
