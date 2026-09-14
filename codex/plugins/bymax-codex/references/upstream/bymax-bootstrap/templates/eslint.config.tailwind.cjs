/**
 * ESLint flat-config OVERLAY — Tailwind CSS rules.
 *
 * Layer that any project using Tailwind can spread on top of its base
 * stack config (Next / Vite-React / Expo-RN / Node). Detects the project's
 * Tailwind major version and applies the right rule set:
 *
 *   - Tailwind 4.x → adds canonical-class hints (suggestCanonicalClasses-style),
 *                    enforces the new shorthand for CSS variables and ARIA
 *                    boolean variants.
 *   - Tailwind 3.x (or NativeWind 4 which ships against Tailwind 3) → keeps
 *                  the long form (`bg-[var(--x)]`, `aria-[invalid=true]:`)
 *                  because the canonical shortcuts don't exist on v3 and
 *                  would fail to compile.
 *
 * Required deps:
 *   pnpm add -D eslint-plugin-tailwindcss
 *   # And the standard Prettier plugin (sorts classes — works on v3 and v4):
 *   pnpm add -D prettier-plugin-tailwindcss
 *   # Then in .prettierrc.json:
 *   #   { "plugins": ["prettier-plugin-tailwindcss"] }
 *
 * Usage in a project's eslint.config.cjs:
 *
 *   const stack = require('./eslint.config.next.cjs');     // or expo-rn / vite-react
 *   const tailwind = require('./eslint.config.tailwind.cjs');
 *
 *   module.exports = [...stack, ...tailwind()];
 *
 * The factory accepts an options object so projects can override detection
 * if their package.json doesn't follow the convention.
 */

const fs = require('node:fs');
const path = require('node:path');

const tailwindPlugin = require('eslint-plugin-tailwindcss');

/**
 * Detect the major version of Tailwind installed in the project.
 * Reads ./package.json relative to the cwd. Returns 3 or 4.
 * Defaults to 4 when ambiguous (modern bias).
 */
function detectTailwindMajor() {
  try {
    const pkgPath = path.resolve(process.cwd(), 'package.json');
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    const all = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
    const tw = all.tailwindcss;
    if (!tw) return 4; // no tailwind found → modern default
    // Strip leading semver range chars and read the major.
    const major = parseInt(String(tw).replace(/^[\^~>=<]+/, '').split('.')[0], 10);
    if (Number.isFinite(major)) return major;
  } catch {
    // ignore — fall through to default
  }
  return 4;
}

/**
 * Build the Tailwind ESLint overlay.
 *
 * @param {object} [options]
 * @param {3|4}   [options.tailwindMajor] - Force the major version. Default: auto-detect.
 * @param {string[]} [options.callees]    - Function names whose first string-arg is a class list. Default: ['cn','clsx','cva','tw','classNames'].
 * @returns {import('eslint').Linter.Config[]} Flat config blocks ready to spread.
 */
module.exports = function tailwindOverlay(options = {}) {
  const major = options.tailwindMajor ?? detectTailwindMajor();
  const callees = options.callees ?? ['cn', 'clsx', 'cva', 'tw', 'classNames'];

  const blocks = [
    // Base — always on (works for v3 and v4).
    {
      plugins: { tailwindcss: tailwindPlugin },
      rules: {
        // Sort classes deterministically.
        'tailwindcss/classnames-order': 'warn',
        // Catch shorthand opportunities (mx-2 my-2 → m-2, etc.).
        'tailwindcss/enforces-shorthand': 'warn',
        // Forbid two utilities that target the same property in the same string.
        'tailwindcss/no-contradicting-classname': 'error',
        // Forbid arbitrary values that have a token equivalent (encourages design-system tokens).
        'tailwindcss/no-arbitrary-value': 'off', // off by default — too noisy for design-token-driven projects
        // Forbid completely unknown classnames.
        'tailwindcss/no-custom-classname': 'off', // off by default — many projects mix shadcn / custom utilities
      },
      settings: {
        tailwindcss: {
          callees,
        },
      },
    },
  ];

  if (major >= 4) {
    // Tailwind v4-only: enforce canonical shortcuts.
    // The official eslint-plugin-tailwindcss does not yet have a dedicated rule
    // for the suggestCanonicalClasses warning, so we use no-restricted-syntax
    // with regex selectors against string literals inside JSX className / cn() / etc.
    blocks.push({
      files: ['**/*.{ts,tsx,js,jsx}'],
      rules: {
        'no-restricted-syntax': [
          'warn',
          {
            // Match: bg-[var(--x)], border-[var(--glass-border)], etc.
            selector:
              "Literal[value=/[a-zA-Z][a-zA-Z0-9-]*-\\[var\\(--[a-zA-Z0-9-]+\\)\\]/]",
            message:
              'Tailwind v4 — use the canonical CSS variable shorthand: e.g., `bg-(--surface)` instead of `bg-[var(--surface)]`. See /bymax-workflow:standards § 11a.',
          },
          {
            // Match: aria-[invalid=true]:, aria-[disabled=true]:, etc. for the standard boolean variants.
            selector:
              "Literal[value=/aria-\\[(invalid|disabled|pressed|expanded|hidden|selected|checked|busy|modal|required|readonly)=true\\]:/]",
            message:
              'Tailwind v4 — use the canonical ARIA short variant: e.g., `aria-invalid:` instead of `aria-[invalid=true]:`. See /bymax-workflow:standards § 11a.',
          },
          {
            // Match: any-utility-[<N>rem] where N maps to a default-scale token.
            // Common values: 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 20, 24, 32, 40, 48, 56, 64, 72, 80, 96.
            // Canonical token = rem × 4 (e.g., 8rem → 32 → min-w-32).
            // The regex is conservative — only matches integer / half-integer rems likely to be on-scale.
            selector:
              "Literal[value=/[a-zA-Z][a-zA-Z0-9-]*-\\[(0\\.5|0\\.25|0\\.75|[1-9][0-9]?|0)(\\.[05])?rem\\]/]",
            message:
              'Tailwind v4 — arbitrary `[Nrem]` likely matches a default-scale token. Use the canonical class (token = rem × 4 for spacing/sizing; e.g., `min-w-[8rem]` → `min-w-32`, `p-[1rem]` → `p-4`). Off-scale values are fine — keep `[Nrem]` only when no token matches. See /bymax-workflow:standards § 11a.',
          },
          {
            // Match: bg-gradient-to-{r,l,t,b,tr,tl,br,bl} (renamed to bg-linear-to-* in v4).
            selector:
              "Literal[value=/(?<![a-zA-Z0-9-])bg-gradient-to-(?:r|l|t|b|tr|tl|br|bl)(?![a-zA-Z0-9-])/]",
            message:
              'Tailwind v4 — `bg-gradient-to-*` was renamed to `bg-linear-to-*` (v4 added radial / conic gradients). See /bymax-workflow:standards § 11a "Renamed utilities".',
          },
          {
            // Match: scale shifts — bare names (shadow, drop-shadow, blur, backdrop-blur, rounded)
            // and their old -sm variants. Caught with word boundaries so we don't match shadow-md, etc.
            selector:
              "Literal[value=/(?<![a-zA-Z0-9-])(shadow|drop-shadow|blur|backdrop-blur|rounded)(-sm)?(?![a-zA-Z0-9/-])/]",
            message:
              'Tailwind v4 — scale shift: `shadow`/`drop-shadow`/`blur`/`backdrop-blur`/`rounded` (or their `-sm` variants) were renamed (`shadow` → `shadow-sm`, `shadow-sm` → `shadow-xs`, etc.). See /bymax-workflow:standards § 11a "Renamed utilities".',
          },
          {
            // Match: outline-none, decoration-clone, decoration-slice, overflow-ellipsis,
            //        flex-shrink-{n}, flex-grow-{n}.
            selector:
              "Literal[value=/(?<![a-zA-Z0-9-])(outline-none|decoration-(?:clone|slice)|overflow-ellipsis|flex-(?:shrink|grow)(?:-[0-9]+)?)(?![a-zA-Z0-9-])/]",
            message:
              'Tailwind v4 — utility was renamed: `outline-none` → `outline-hidden`, `decoration-clone` → `box-decoration-clone`, `decoration-slice` → `box-decoration-slice`, `overflow-ellipsis` → `text-ellipsis`, `flex-shrink-*` → `shrink-*`, `flex-grow-*` → `grow-*`. See /bymax-workflow:standards § 11a "Renamed utilities".',
          },
          {
            // Match: standalone opacity utilities (bg-opacity-*, text-opacity-*, etc.).
            // In v4 use the slash modifier on the color: bg-blue-500/50.
            selector:
              "Literal[value=/(?<![a-zA-Z0-9-])(bg|text|border|divide|placeholder|ring)-opacity-[0-9]+(?![a-zA-Z0-9-])/]",
            message:
              'Tailwind v4 — standalone opacity utilities are deprecated. Use the slash modifier on the color (e.g., `bg-blue-500/50` instead of `bg-blue-500 bg-opacity-50`). See /bymax-workflow:standards § 11a "Renamed utilities".',
          },
          {
            // z-[N] → z-N (v4 supports bare integers for z-index without brackets).
            selector:
              "Literal[value=/(?<![a-zA-Z0-9-])z-\\[[0-9]+\\](?![a-zA-Z0-9-])/]",
            message:
              'Tailwind v4 — `z-[N]` can drop the brackets: `z-[200]` → `z-200`. See /bymax-workflow:standards § 11a.',
          },
          {
            // backdrop-blur-[Npx] / blur-[Npx] → named filter token (on-scale px values only).
            selector:
              "Literal[value=/(?<![a-zA-Z0-9-])(backdrop-blur|blur)-\\[(4|8|12|16|24|40|64)px\\](?![a-zA-Z0-9-])/]",
            message:
              'Tailwind v4 — use the named filter token: 4px=xs, 8px=sm, 12px=md, 16px=lg, 24px=xl, 40px=2xl, 64px=3xl. E.g., `backdrop-blur-[12px]` → `backdrop-blur-md`. See /bymax-workflow:standards § 11a.',
          },
          {
            // -bottom-0, -top-0, -left-0, -right-0, -inset-0, -m-0, -p-0, etc. (negative zero = zero).
            selector:
              "Literal[value=/(?<![a-zA-Z0-9])-(?:top|right|bottom|left|inset(?:-[xy])?|m[xytblrsv]?|p[xytblrsv]?)-0(?![a-zA-Z0-9-])/]",
            message:
              'Negative zero equals zero — use the positive form: `-bottom-0` → `bottom-0`, `-m-0` → `m-0`, etc.',
          },
        ],
      },
    });
  }

  return blocks;
};

// Convenience: allow `module.exports.detect = detectTailwindMajor` for projects
// that want to pick up the version themselves.
module.exports.detectTailwindMajor = detectTailwindMajor;
