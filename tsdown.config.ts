/**
 * Build configuration.
 *
 * The build emits one ESM entry. Every DeepSeek Harness package stays
 * external: the host supplies one shared copy, and a second copy in the
 * bundle would break service identity. Runtime dependencies stay external
 * too, so that `ws` resolves from this package's own `node_modules`.
 *
 * @module dsh-ai-love/tsdown.config
 */

import { defineConfig } from 'tsdown'

export default defineConfig({
  entry: ['src/index.ts'],
  outDir: 'lib',
  format: 'esm',
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  clean: true,
  sourcemap: false,
  deps: {
    neverBundle: [/^@deepseek-ai\//],
  },
})
