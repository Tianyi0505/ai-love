/**
 * Tests of the workspace scaffold.
 *
 * @module dsh-luoyu/test/workspace.test
 */

import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import type { PluginLogger } from '../src/context.ts'
import {
  INSTRUCTION_FILE,
  MEMORY_DIR,
  MEMORY_FILES,
  PERSONA_FILE,
  instructionBody,
  memoryBody,
  memoryPath,
  personaBody,
  personaText,
  readPersona,
  scaffoldWorkspace,
} from '../src/workspace.ts'

const silent: PluginLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
}

/** Create a temporary directory and remove it after the test. */
async function withTempDir(body: (dir: string) => Promise<void>): Promise<void> {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-luoyu-workspace-'))
  try {
    await body(dir)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

test('creates the instruction file, the persona, and every memory file', async () => {
  await withTempDir(async dir => {
    const result = await scaffoldWorkspace(dir, 'You are Ada.', silent)
    assert.equal(result.created.length, 2 + MEMORY_FILES.length)
    assert.deepEqual(result.kept, [])

    const instruction = await readFile(join(dir, INSTRUCTION_FILE), 'utf8')
    assert.match(instruction, /long-term memory/)
    const persona = await readFile(join(dir, PERSONA_FILE), 'utf8')
    assert.match(persona, /You are Ada\./)
    for (const name of MEMORY_FILES) {
      const body = await readFile(memoryPath(dir, name), 'utf8')
      assert.ok(body.length > 0)
    }
  })
})

test('keeps a file that the operator already edited', async () => {
  await withTempDir(async dir => {
    await scaffoldWorkspace(dir, 'You are Ada.', silent)
    const path = join(dir, PERSONA_FILE)
    await writeFile(path, '# Mine\n', 'utf8')
    const result = await scaffoldWorkspace(dir, 'You are Ada.', silent)
    assert.ok(result.kept.includes(path))
    assert.equal(await readFile(path, 'utf8'), '# Mine\n')
  })
})

test('reads the persona back', async () => {
  await withTempDir(async dir => {
    await scaffoldWorkspace(dir, 'You are Ada.', silent)
    const persona = await readPersona(dir)
    assert.match(persona, /You are Ada\./)
  })
})

test('returns the empty persona when the file is absent', async () => {
  await withTempDir(async dir => {
    assert.equal(await readPersona(dir), '')
  })
})

test('the instruction file names every memory file', () => {
  const body = instructionBody()
  for (const name of MEMORY_FILES) assert.ok(body.includes(name), `the instruction file must name ${name}`)
  assert.ok(body.includes(MEMORY_DIR))
  assert.ok(body.includes(PERSONA_FILE))
})

test('the persona body repeats the configured text', () => {
  assert.match(personaBody('  You are Ada.  '), /You are Ada\./)
})

test('reads only the editable persona from the Markdown file', () => {
  assert.equal(personaText(personaBody('You are Ada.')), 'You are Ada.')
  assert.equal(personaText('# Persona\n\nYou are Robin.'), 'You are Robin.')
})

test('each memory file has its own body', () => {
  const bodies = new Set(MEMORY_FILES.map(name => memoryBody(name)))
  assert.equal(bodies.size, MEMORY_FILES.length)
})

test('an unknown memory file gets a plain heading', () => {
  assert.equal(memoryBody('other.md'), '# other.md\n')
})
