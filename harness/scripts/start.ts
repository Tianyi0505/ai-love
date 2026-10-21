import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, realpathSync, symlinkSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { networkInterfaces } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

interface ProfileManifest {
  dependencies: Record<string, string>
}

interface DshManifest {
  bin?: string | Record<string, string>
}

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const harnessDirectory = resolve(scriptDirectory, '..')
const pluginDirectory = resolve(harnessDirectory, '..')
const templateDirectory = join(harnessDirectory, 'profile-template')
const homeDirectory = resolve(process.env.DSH_HOME || join(harnessDirectory, '.runtime'))
const profileName = process.env.AILOVE_DSH_PROFILE || 'ai-love'
const profileDirectory = join(homeDirectory, 'profiles', profileName)
const workspaceDirectory = resolve(
  process.env.AILOVE_WORKSPACE_DIRECTORY ?? process.env.AILOVE_ROOT ?? join(harnessDirectory, '..'),
)

function normalizedPath(path: string): string {
  return path.replaceAll('\\', '/')
}

function ensureProfile(): void {
  mkdirSync(profileDirectory, { recursive: true })
  const manifestPath = join(profileDirectory, 'package.json')
  if (!existsSync(manifestPath)) {
    const manifest = JSON.parse(readFileSync(join(templateDirectory, 'package.json'), 'utf8')) as ProfileManifest
    manifest.dependencies['@ai-love/deepseek-harness-plugin'] = `link:${normalizedPath(pluginDirectory)}`
    writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, { flag: 'wx' })
  }

  const patchPath = join(profileDirectory, 'cordis.patch.yml')
  if (!existsSync(patchPath)) {
    writeFileSync(patchPath, readFileSync(join(templateDirectory, 'cordis.patch.yml')), { flag: 'wx' })
  }

  const scopeDirectory = join(profileDirectory, 'node_modules', '@ai-love')
  const bundleLink = join(scopeDirectory, 'deepseek-harness-plugin')
  mkdirSync(scopeDirectory, { recursive: true })
  if (existsSync(bundleLink)) {
    const current = realpathSync.native(bundleLink)
    const expected = realpathSync.native(pluginDirectory)
    if (current !== expected) {
      throw new Error(`Profile bundle path points at ${current}; expected ${expected}`)
    }
  } else {
    symlinkSync(pluginDirectory, bundleLink, process.platform === 'win32' ? 'junction' : 'dir')
  }
}

function containerAddress(): string {
  for (const addresses of Object.values(networkInterfaces())) {
    for (const address of addresses || []) {
      if (!address.internal && address.family === 'IPv4') return address.address
    }
  }
  throw new Error('AILOVE_DSH_HOST=auto but no non-loopback IPv4 address is available')
}

ensureProfile()
mkdirSync(workspaceDirectory, { recursive: true })

const require = createRequire(import.meta.url)
const dshManifestPath = require.resolve('@deepseek-ai/dsh/package.json')
const dshManifest = JSON.parse(readFileSync(dshManifestPath, 'utf8')) as DshManifest
const binEntry = typeof dshManifest.bin === 'string' ? dshManifest.bin : dshManifest.bin?.dsh
if (!binEntry) throw new Error('@deepseek-ai/dsh does not declare the dsh executable')

const forwarded = process.argv.slice(2)
const configuredHost = process.env.AILOVE_DSH_HOST
if (configuredHost && !forwarded.includes('--host') && !forwarded.includes('--dump-config')) {
  forwarded.push('--host', configuredHost === 'auto' ? containerAddress() : configuredHost)
}

const child = spawn(process.execPath, [resolve(dirname(dshManifestPath), binEntry), '--profile', profileName, ...forwarded], {
  cwd: workspaceDirectory,
  env: { ...process.env, DSH_HOME: homeDirectory },
  stdio: 'inherit',
})

let forwardingSignal = false
for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.once(signal, () => {
    if (forwardingSignal) return
    forwardingSignal = true
    child.kill(signal)
  })
}

child.once('error', (error: Error) => {
  console.error(`Failed to start DeepSeek Harness: ${error.message}`)
  process.exitCode = 1
})

child.once('exit', (code: number | null, signal: NodeJS.Signals | null) => {
  process.exitCode = code ?? (signal ? 1 : 0)
})
