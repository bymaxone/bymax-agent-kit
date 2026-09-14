/**
 * ESLint flat-config — Next.js + TypeScript.
 *
 * Layered on top of the universal base. Tested against Next 15+/16.
 *
 * Required deps:
 *   pnpm add -D eslint @eslint/eslintrc eslint-config-next \
 *     @typescript-eslint/parser @typescript-eslint/eslint-plugin \
 *     eslint-plugin-import eslint-plugin-react-hooks eslint-plugin-security \
 *     eslint-plugin-prettier eslint-config-prettier eslint-import-resolver-typescript
 */

const { FlatCompat } = require('@eslint/eslintrc');
const tsParser = require('@typescript-eslint/parser');
const tsPlugin = require('@typescript-eslint/eslint-plugin');
const reactHooks = require('eslint-plugin-react-hooks');

const universal = require('./eslint.config.universal.cjs');

const compat = new FlatCompat({ baseDirectory: __dirname });

module.exports = [
  // Next preset (loads next/core-web-vitals + react + react-hooks).
  ...compat.extends('next/core-web-vitals', 'next/typescript'),

  // TypeScript layer — strict, type-aware rules.
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: ['./tsconfig.json'],
        tsconfigRootDir: __dirname,
      },
    },
    plugins: { '@typescript-eslint': tsPlugin },
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
    },
  },

  // React hooks discipline.
  {
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
    },
  },

  // No cross-feature imports — orchestrate via app/ or shared/.
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
    ignores: ['.next/', 'public/'],
  },
];
