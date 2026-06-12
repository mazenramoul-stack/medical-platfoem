import js from '@eslint/js';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default [
  { ignores: ['dist/', 'node_modules/'] },

  js.configs.recommended,
  react.configs.flat.recommended,
  // Vite uses the automatic JSX runtime; React import is not required in scope.
  react.configs.flat['jsx-runtime'],
  reactHooks.configs.flat.recommended,

  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: 'detect' },
    },
    rules: {
      // Pragmatic severity for the existing codebase: correctness rules stay
      // "error"; stylistic / noisy rules are relaxed so the current code
      // lints clean without mass rewrites.
      'react/prop-types': 'off',
      'react/display-name': 'off',
      'react/no-unescaped-entities': 'off',
      // react-three-fiber renders three.js objects as JSX; these props are
      // valid r3f attributes, not DOM typos.
      'react/no-unknown-property': ['error', {
        ignore: [
          'args', 'attach', 'castShadow', 'dispose', 'geometry', 'intensity',
          'material', 'object', 'position', 'receiveShadow', 'rotation',
          'emissive', 'emissiveIntensity', 'metalness', 'roughness',
          'transparent', 'wireframe',
        ],
      }],
      // Advisory performance rule (React Compiler lint); the flagged code is
      // the standard fetch-on-mount + setState pattern used across this
      // codebase. Keep visible as a warning, not a blocker.
      'react-hooks/set-state-in-effect': 'warn',
      'no-unused-vars': [
        'error',
        {
          args: 'none',
          caughtErrors: 'none',
          ignoreRestSiblings: true,
          varsIgnorePattern: '^_',
        },
      ],
    },
  },
];
