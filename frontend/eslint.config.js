import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

export default defineConfig([
  globalIgnores(['dist', 'coverage']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [js.configs.recommended, reactHooks.configs.flat.recommended, reactRefresh.configs.vite],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: { ...globals.browser, __VERSAO_APP__: 'readonly' },
      parserOptions: { ecmaFeatures: { jsx: true }, sourceType: 'module' },
    },
    rules: {
      // Componentes (maiúscula) usados só em JSX não contam como não usados.
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
    },
  },
  {
    // Contextos exportam o provedor e o hook de uso no mesmo arquivo.
    files: ['src/contexts/**/*.{js,jsx}'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  {
    // Config, testes e apoio dos testes rodam em Node (globais como `process`), não no navegador.
    files: ['*.config.js', 'src/**/*.test.{js,jsx}', 'src/testes/**/*.{js,jsx}'],
    languageOptions: { globals: globals.node },
  },
])
