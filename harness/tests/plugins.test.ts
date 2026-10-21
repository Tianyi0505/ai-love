import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import test from 'node:test'
import { boot } from '@deepseek-ai/dsh-app-boot'
import { normalizeConversationInput } from '../bundle/src/http-ingress.ts'
import { MarkdownMemory, conversationSessionId } from '../bundle/src/markdown-memory.ts'

const testDirectory = dirname(fileURLToPath(import.meta.url))
const bundleDirectory = resolve(testDirectory, '..', 'bundle')
const repositoryDirectory = resolve(bundleDirectory, '..', '..')

test('the repository exposes one cohesive plugin with no business-plugin dependency surface', async () => {
  const patch = readFileSync(join(bundleDirectory, 'cordis.patch.yml'), 'utf8')
  assert.doesNotMatch(patch, /^\s*(inject|requires):/mu)
  assert.deepEqual([...patch.matchAll(/^\s+- id: (.+)$/gmu)].map(match => match[1]), ['ai-love'])

  const manifest = JSON.parse(readFileSync(join(repositoryDirectory, 'package.json'), 'utf8')) as { exports: Record<string, string> }
  assert.deepEqual(Object.keys(manifest.exports).sort(), ['.', './cordis.patch.yml', './package.json'])

  const plugin = await import('../bundle/src/ai-love.ts')
  assert.equal(plugin.name, 'ai-love')
  assert.equal(typeof plugin.apply, 'function')
  assert.equal(Object.hasOwn(plugin, 'inject'), false)
})

test('each group or private chat maps to one stable and isolated DSH session', () => {
  const privateChat = { platform: 'qq', accountId: 'bot-1', chatType: 'private' as const, chatId: 'person-1' }
  const groupChat = { ...privateChat, chatType: 'group' as const }
  assert.equal(conversationSessionId(privateChat), conversationSessionId({ ...privateChat }))
  assert.notEqual(conversationSessionId(privateChat), conversationSessionId(groupChat))
  assert.notEqual(conversationSessionId(privateChat), conversationSessionId({ ...privateChat, accountId: 'bot-2' }))
})

test('Markdown memory is created inside the selected project directory', async () => {
  const workspace = mkdtempSync(join(tmpdir(), 'ai-love-workspace-'))
  const memory = new MarkdownMemory(workspace, '.ai-love/memory')
  await memory.initialize()
  const result = await memory.ensureConversation({
    platform: 'qq',
    accountId: 'bot-1',
    chatType: 'group',
    chatId: 'group-1',
    aiId: 'luoyu',
  })

  assert.equal(result.conversationDirectory.startsWith(memory.memoryDirectory), true)
  assert.equal(existsSync(join(result.sharedDirectory, 'README.md')), true)
  assert.equal(existsSync(join(result.identityDirectory, 'MEMORY.md')), true)
  assert.equal(existsSync(join(result.conversationDirectory, 'MEMORY.md')), true)
})

test('ingress accepts the native shape and the legacy social-message shape', () => {
  assert.deepEqual(normalizeConversationInput({
    platform: 'qq', accountId: 'bot-1', chatType: 'private', chatId: 'person-1', senderId: 'person-1', text: 'hello',
  }), {
    platform: 'qq', accountId: 'bot-1', chatType: 'private', chatId: 'person-1', aiId: undefined,
    senderId: 'person-1', senderName: undefined, messageId: undefined, text: 'hello',
  })
  assert.deepEqual(normalizeConversationInput({
    platform: 'qq', account_id: 'bot-1', chat: { chat_type: 'group', chat_id: 'group-1' },
    sender: { user_id: 'person-1', name: 'Alice' }, meta: { ai_id: 'luoyu' }, message_id: 'message-1', text: 'hello',
  }), {
    platform: 'qq', accountId: 'bot-1', chatType: 'group', chatId: 'group-1', aiId: 'luoyu',
    senderId: 'person-1', senderName: 'Alice', messageId: 'message-1', text: 'hello',
  })
})

test('the real Cordis loader can load and dispose the plugin without the optional agent service', async () => {
  const root = mkdtempSync(join(tmpdir(), 'ai-love-loader-'))
  const workspace = join(root, 'workspace')
  const config = join(root, 'cordis.yml')
  const row = [
    '- id: ai-love',
    `  name: ${JSON.stringify(pathToFileURL(join(bundleDirectory, 'src', 'ai-love.ts')).href)}`,
    '  config:',
    `    workspaceDirectory: ${JSON.stringify(workspace)}`,
    '    ingressPort: 0',
  ].join('\n')
  writeFileSync(config, `${row}\n`)

  const ctx = await boot('ai-love-plugin-loader-test', config)
  try {
    assert.equal(existsSync(join(workspace, '.ai-love', 'memory', 'shared', 'README.md')), true)
  } finally {
    await ctx.fiber.dispose()
  }
})
