import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // The app intentionally uses provider+hook exports in context modules.
      // Keep this visible during development without making CI unusable.
      'react-refresh/only-export-components': 'warn',
      // Existing data pages load remote state from useEffect. The React 19
      // compiler rule is too aggressive for this codebase until those pages are
      // migrated to a query/cache abstraction.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
])
