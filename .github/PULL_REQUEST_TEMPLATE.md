## Summary

<!-- One paragraph: what changes and why. Link the issue this closes. -->

Closes #

## Type of change

- [ ] 🐛 Bug fix (non-breaking)
- [ ] ✨ New feature (non-breaking, additive)
- [ ] 💥 Breaking change (existing slash commands, plugin layout, or template behavior changed)
- [ ] 📝 Documentation only
- [ ] 🧹 Internal refactor (no behavior change)

## Plugin(s) affected

- [ ] `bymax-workflow`
- [ ] `bymax-quality`
- [ ] `bymax-bootstrap`
- [ ] `bymax-mobile`
- [ ] `bymax-all` (meta — only because a sibling changed)
- [ ] Repo-level (README, CI, etc.)

## Checklist

- [ ] `./scripts/validate.sh` passes (marketplace.json + every touched plugin.json valid).
- [ ] If you added a slash command — its YAML frontmatter has a clear English `description` field with PT/EN trigger phrases.
- [ ] If you added an agent — frontmatter includes `model: sonnet` (or `opus`, never `haiku`).
- [ ] If you added a skill — folder layout follows `<skill-name>/SKILL.md` (the new convention).
- [ ] If you added a hook — `chmod +x` and the script has a happy-path `exit 0`.
- [ ] No new `// @ts-ignore`, `// eslint-disable*`, `as any`, or other suppression comments anywhere.
- [ ] If you bumped a plugin's `plugin.json` `version`, you also bumped `marketplace.json` `version` appropriately (semver).
- [ ] Updated [`CHANGELOG.md`](../CHANGELOG.md) under `[Unreleased]` with a one-liner.
- [ ] Commit message follows [Conventional Commits](https://www.conventionalcommits.org/).

## Manual test

<!-- How did you verify this works? Steps + outcome. -->

```bash
# Example
claude plugin marketplace add ./
claude plugin install bymax-quality@bymax-agent-kit
# /tdd ... worked as expected
```

## Screenshots / recordings (optional)

<!-- If a UX-affecting change. -->
