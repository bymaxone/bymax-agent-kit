/**
 * ESLint flat-config — Vite + React + TypeScript.
 *
 * Layered on top of the universal base.
 *
 * Required deps:
 *   pnpm add -D eslint typescript-eslint \
 *     eslint-plugin-react eslint-plugin-react-hooks eslint-plugin-react-refresh \
 *     eslint-plugin-import eslint-plugin-security \
 *     eslint-plugin-prettier eslint-config-prettier eslint-import-resolver-typescript \
 *     globals
 */

const js = require('@eslint/js');
const tseslint = require('typescript-eslint');
const react = require('eslint-plugin-react');
const reactHooks = require('eslint-plugin-react-hooks');
const reactRefresh = require('eslint-plugin-react-refresh');
const globals = require('globals');

const universal = require('./eslint.config.universal.cjs');

module.exports = tseslint.config(
  // Base JS rules.
  js.configs.recommended,

  // TypeScript — strict + type-checked.
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        project: ['./tsconfig.json', './tsconfig.node.json'],
        tsconfigRootDir: __dirname,
      },
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'separate-type-imports' },
      ],
      '@typescript-eslint/no-non-null-assertion': 'warn',
      '@typescript-eslint/ban-ts-comment': [
        'error',
        {
          'ts-ignore': true,
          'ts-expect-error': 'allow-with-description',
          'ts-nocheck': true,
        },
      ],
      // Vite's tsconfig.node.json is for build tooling, not app code.
    },
  },

  // React + hooks + refresh.
  {
    files: ['**/*.{jsx,tsx}'],
    plugins: { react, 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    settings: { react: { version: 'detect' } },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'react/prop-types': 'off', // covered by TS
    },
  },

  // No cross-feature imports.
  {
    files: ['src/features/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/features/*/!(index)', '@/features/*/!(index)/**'],
              message:
                'Cross-feature imports must go through the feature barrel (index.ts). See /bymax-workflow:standards §5.',
            },
          ],
        },
      ],
    },
  },

  // Universal layer (security, import-order, prettier, banned constructs).
  ...universal({ tsconfigPath: './tsconfig.json' }),

  {
    ignores: ['dist/', 'public/'],
  },
);
