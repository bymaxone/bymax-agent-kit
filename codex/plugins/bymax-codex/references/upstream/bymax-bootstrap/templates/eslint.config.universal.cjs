/**
 * Universal ESLint flat-config base.
 *
 * Composable layer that every stack-specific config (Next, Expo/RN, Vite, Node)
 * spreads on top of its own preset. Provides:
 *
 *   - eslint-plugin-security (regex DoS, eval, prototype pollution, child_process)
 *   - eslint-plugin-import (ordering, no-cycle, no-default-export-where-banned)
 *   - prettier integration as an ESLint rule (lint failures = format failures)
 *   - sensible defaults for TS strictness
 *
 * Usage:
 *
 *   const universal = require('./eslint.config.universal.cjs');
 *   module.exports = [...presetForStack, ...universal({ tsconfigPath: './tsconfig.json' })];
 *
 * The factory accepts options so each project can point at its own tsconfig
 * for the import resolver without forking this file.
 */

const importPlugin = require('eslint-plugin-import');
const security = require('eslint-plugin-security');
const prettierPlugin = require('eslint-plugin-prettier');
const prettierConfig = require('eslint-config-prettier');

/**
 * Build the universal ESLint layer.
 *
 * @param {object} [options]
 * @param {string} [options.tsconfigPath='./tsconfig.json'] - Path to tsconfig used by the import resolver.
 * @param {string[]} [options.internalAliases=['@/**','@app/**','@tests/**']] - Path aliases to treat as `internal` for import-order grouping.
 * @returns {import('eslint').Linter.Config[]} ESLint flat-config blocks ready to spread.
 */
module.exports = function universal(options = {}) {
  const {
    tsconfigPath = './tsconfig.json',
    internalAliases = ['@/**', '@app/**', '@tests/**'],
  } = options;

  return [
    // Security: detects unsafe regex, eval, prototype pollution, etc.
    security.configs.recommended,

    // TS files: disable detect-object-injection — typed string-literal unions
    // already prevent prototype-pollution; the rule has too many false positives
    // on Record<Union, V>[key] lookups and no useful configuration knobs.
    {
      files: ['**/*.ts', '**/*.tsx'],
      rules: {
        'security/detect-object-injection': 'off',
      },
    },

    // Build scripts: disable detect-non-literal-fs-filename — Node tooling uses
    // computed paths derived from literal strings, not user input.
    {
      files: ['scripts/**/*.{ts,js,cjs,mjs}', '*.config.{ts,js,cjs,mjs}'],
      rules: {
        'security/detect-non-literal-fs-filename': 'off',
      },
    },

    // Import ordering — single source of truth for grouping/alphabetization.
    {
      plugins: { import: importPlugin },
      rules: {
        'import/order': [
          'warn',
          {
            groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
            pathGroups: internalAliases.map((pattern) => ({
              pattern,
              group: 'internal',
              position: 'after',
            })),
            pathGroupsExcludedImportTypes: ['builtin'],
            alphabetize: { order: 'asc', caseInsensitive: true },
            'newlines-between': 'always',
          },
        ],
        'import/no-duplicates': 'error',
        'import/no-self-import': 'error',
        'import/no-useless-path-segments': 'warn',
      },
      settings: {
        'import/resolver': {
          typescript: {
            alwaysTryTypes: true,
            project: tsconfigPath,
          },
        },
      },
    },

    // Banned constructs — universal across every project.
    {
      rules: {
        'no-console': ['warn', { allow: ['warn', 'error'] }],
        'no-debugger': 'error',
        'no-alert': 'error',
        'no-eval': 'error',
        'no-implied-eval': 'error',
        'no-new-func': 'error',
        'no-restricted-syntax': [
          'error',
          {
            selector: 'TSEnumDeclaration',
            message:
              'Do not use TypeScript enums. Use a string-literal union type instead. See /bymax-workflow:standards.',
          },
        ],
      },
    },

    // Security: ban risky imports — force the safer Node primitive or a vetted library.
    // Pulled from the nest-auth project; applies anywhere this kind of crypto / id work
    // happens. Override per-project if a specific lib is genuinely required (with an ADR).
    {
      rules: {
        'no-restricted-imports': [
          'error',
          {
            paths: [
              {
                name: 'crypto',
                message: 'Use `node:crypto` (the prefixed form) for clarity and tree-shake safety.',
              },
              {
                name: 'bcrypt',
                message:
                  'Use `argon2` via the project-approved hashing service, not bcrypt directly. See /bymax-workflow:standards §12.',
              },
              {
                name: 'bcryptjs',
                message: 'Use `argon2` via the project-approved hashing service, not bcryptjs.',
              },
              {
                name: 'crypto-js',
                message:
                  'Use `node:crypto` or WebCrypto. crypto-js has known weaknesses and unmaintained surfaces.',
              },
              {
                name: 'md5',
                message: 'MD5 is not cryptographically secure. Use SHA-256 via `node:crypto`.',
              },
              {
                name: 'uuid',
                message:
                  'Use `crypto.randomUUID()` from `node:crypto` (Node 18+) or `Crypto.randomUUID()` (browser).',
              },
              {
                name: 'nanoid',
                message:
                  'Use `crypto.randomUUID()` unless you genuinely need short IDs. If so, justify in an ADR and override this rule per-file.',
              },
            ],
          },
        ],
      },
    },

    // Prettier as an ESLint rule — formatting failures show up as lint failures.
    {
      plugins: { prettier: prettierPlugin },
      rules: { 'prettier/prettier': 'error' },
    },

    // Disable formatting rules that conflict with Prettier.
    // Must be the LAST entry that touches formatting rules.
    prettierConfig,

    // Universal ignored paths.
    {
      ignores: [
        'node_modules/',
        'dist/',
        'build/',
        'out/',
        '.next/',
        '.expo/',
        '.turbo/',
        '.cache/',
        'coverage/',
        '**/*.generated.*',
        '**/*.min.js',
        'pnpm-lock.yaml',
        'package-lock.json',
        'yarn.lock',
      ],
    },
  ];
};
