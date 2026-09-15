/**
 * lint-staged — runs ESLint --fix and Prettier on staged files only.
 * Wired through Husky's pre-commit hook.
 */
module.exports = {
  '*.{ts,tsx,js,jsx,cjs,mjs}': ['eslint --fix', 'prettier --write'],
  '*.{json,jsonc,md,yml,yaml,css,html}': ['prettier --write'],
};
