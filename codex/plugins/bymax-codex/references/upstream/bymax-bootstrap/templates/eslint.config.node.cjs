/**
 * ESLint flat-config — Node.js backend (Express / Fastify / Hono / NestJS / plain Node).
 *
 * Layered on top of the universal base.
 *
 * Required deps:
 *   pnpm add -D eslint typescript-eslint \
 *     eslint-plugin-import eslint-plugin-security eslint-plugin-n \
 *     eslint-plugin-prettier eslint-config-prettier eslint-import-resolver-typescript \
 *     globals
 */

const js = require('@eslint/js');
const tseslint = require('typescript-eslint');
const nodePlugin = require('eslint-plugin-n');
const globals = require('globals');

const universal = require('./eslint.config.universal.cjs');

module.exports = tseslint.config(
  // Base JS rules.
  js.configs.recommended,

  // Node best-practices.
  nodePlugin.configs['flat/recommended'],

  // TypeScript — strict + type-checked.
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,

  {
    files: ['**/*.{ts,js,cjs,mjs}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.node,
      parserOptions: {
        project: ['./tsconfig.json'],
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
      // Node-specific guards.
      'n/no-process-exit': 'error',
      'n/no-deprecated-api': 'error',
      'n/prefer-node-protocol': 'error',
      'no-process-env': 'off', // env access is legitimate at the boundary; gated by app code.
    },
  },

  // No cross-feature imports.
  {
    files: ['src/features/**/*.{ts,js}'],
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
    ignores: ['dist/', 'build/'],
  },
);
