/**
 * Tests of the browser Settings module contract.
 *
 * @module dsh-ai-love/test/client.test
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { runInNewContext } from 'node:vm'
import test from 'node:test'

test('declares the client packages that provide its services', async () => {
  const manifestText = await readFile(new URL('../package.json', import.meta.url), 'utf8')
  const manifest = JSON.parse(manifestText) as { dsh: { client: { inject: string[] } } }
  assert.ok(manifest.dsh.client.inject.includes('@deepseek-ai/dsh-client-locale'))
  assert.ok(manifest.dsh.client.inject.includes('@deepseek-ai/dsh-client-ui-renderer'))
  assert.ok(manifest.dsh.client.inject.includes('@deepseek-ai/dsh-client-ui-settings'))
})

test('registers an AI Love section with the Harness module loader', async () => {
  const source = await readFile(new URL('../client.js', import.meta.url), 'utf8')
  let registration: { id: string; factory: (require: (name: string) => unknown) => ClientPlugin } | undefined
  runInNewContext(source, {
    window: {
      __ModuleLoader__: {
        load(value: typeof registration extends infer T ? NonNullable<T> : never) {
          registration = value as NonNullable<typeof registration>
        },
      },
    },
  })
  assert.ok(registration)
  assert.equal(registration.id, 'dsh-ai-love')

  const plugin = registration.factory(name => {
    assert.equal(name, 'react')
    return { createElement: () => null }
  })
  assert.equal(plugin.inject.join(','), 'slots,locale')

  let options: Record<string, unknown> | undefined
  let component: unknown
  let dictionary: { en: Record<string, string>; zh: Record<string, string> } | undefined
  plugin.apply({
    effect(effect) { effect() },
    locale: {
      register(_namespace, value) { dictionary = value },
      bind() { return key => dictionary?.en[key] || key },
    },
    slots: {
      inject(_slot, register) { register() },
      register(value, page) {
        options = value
        component = page
        return () => undefined
      },
    },
  })
  assert.equal(options?.name, 'settings.section')
  assert.equal(options?.id, 'ai-love')
  assert.equal(typeof options?.label, 'function')
  assert.equal((options?.label as () => string)(), 'AI Love')
  assert.equal(typeof component, 'function')
  assert.equal(dictionary?.zh.workspace, 'AI 工作区')
  assert.equal(dictionary?.en.title, 'Make your QQ companion yours')
})

interface ClientPlugin {
  inject: string[]
  apply(context: {
    effect(effect: () => unknown, label: string): void
    locale: {
      register(namespace: string, bundles: { en: Record<string, string>; zh: Record<string, string> }): void
      bind(namespace: string): (key: string) => string
    }
    slots: {
      inject(slot: string, register: () => void): void
      register(options: Record<string, unknown>, component: unknown): () => void
    }
  }): void
}

