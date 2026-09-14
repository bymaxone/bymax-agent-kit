/**
 * ESLint flat-config — Expo / React Native + TypeScript.
 *
 * Layered on top of the universal base. Modeled after the bymax.bio setup.
 *
 * Required deps:
 *   pnpm add -D eslint eslint-config-expo \
 *     eslint-plugin-import eslint-plugin-react-hooks eslint-plugin-security \
 *     eslint-plugin-prettier eslint-config-prettier eslint-import-resolver-typescript
 */

const { defineConfig } = require('eslint/config');
const expo = require('eslint-config-expo/flat');
const reactHooks = require('eslint-plugin-react-hooks');

const universal = require('./eslint.config.universal.cjs');

module.exports = defineConfig([
  // Expo preset — includes import, react, react-hooks, @typescript-eslint.
  ...expo,

  // Stronger React hooks discipline.
  {
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
    },
  },

  // TypeScript strictness on top of expo-config-expo defaults.
  // Mirrors the rules used in eslint.config.next.cjs / vite-react.cjs / node.cjs
  // so type-import discipline and any-bans are consistent across stacks.
  {
    files: ['**/*.{ts,tsx}'],
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
    ignores: ['ios/', 'android/', '.expo/'],
  },
]);
