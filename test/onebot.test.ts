/**
 * Tests of the OneBot client helpers.
 *
 * The tests start a local HTTP server that stands in for NapCat. They do not
 * start a WebSocket server, so the reconnect loop stays inert.
 *
 * @module dsh-ai-love/test/onebot.test
 */

import assert from 'node:assert/strict'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import test from 'node:test'
import type { PluginLogger } from '../src/context.ts'
import { OneBotActionError, OneBotClient } from '../src/onebot/client.ts'
import { segmentsOf } from '../src/onebot/types.ts'

const silent: PluginLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
}

/** One recorded action call. */
interface Recorded {
  action: string
  body: unknown
  authorization: string | undefined
}

/** Start a stub NapCat that records each action call. */
async function startStub(
  reply: (action: string, body: unknown) => { status?: number; payload: unknown },
): Promise<{ url: string; calls: Recorded[]; close(): Promise<void> }> {
  const calls: Recorded[] = []
  const server: Server = createServer((request, response) => {
    const chunks: Buffer[] = []
    request.on('data', chunk => chunks.push(chunk as Buffer))
    request.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8')
      const action = (request.url ?? '/').replace(/^\//, '')
      const body = raw.length > 0 ? JSON.parse(raw) : undefined
      calls.push({ action, body, authorization: request.headers.authorization })
      const result = reply(action, body)
      response.statusCode = result.status ?? 200
      response.setHeader('content-type', 'application/json')
      response.end(JSON.stringify(result.payload))
    })
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address() as AddressInfo
  return {
    url: `http://127.0.0.1:${address.port}`,
    calls,
    close: () =>
      new Promise<void>((resolve, reject) => {
        server.close(error => (error === undefined ? resolve() : reject(error)))
      }),
  }
}

/** Build a client that points at one stub. */
function clientFor(url: string, accessToken?: string): OneBotClient {
  return new OneBotClient(
    {
      wsUrl: 'ws://127.0.0.1:1',
      httpUrl: url,
      ...(accessToken === undefined ? {} : { accessToken }),
      actionTimeoutMs: 2000,
    },
    { onMessage: () => undefined },
    silent,
  )
}

test('sends a private message with a numeric user identity', async () => {
  const stub = await startStub(() => ({ payload: { status: 'ok', retcode: 0, data: { message_id: 1 } } }))
  try {
    await clientFor(stub.url).sendPrivate('10001', [{ type: 'text', data: { text: 'hi' } }])
    assert.equal(stub.calls.length, 1)
    assert.equal(stub.calls[0]?.action, 'send_private_msg')
    assert.deepEqual(stub.calls[0]?.body, {
      user_id: 10001,
      message: [{ type: 'text', data: { text: 'hi' } }],
    })
  } finally {
    await stub.close()
  }
})

test('sends a group message with a numeric group identity', async () => {
  const stub = await startStub(() => ({ payload: { status: 'ok', retcode: 0, data: { message_id: 2 } } }))
  try {
    await clientFor(stub.url).sendGroup('782795932', [{ type: 'text', data: { text: 'hi' } }])
    assert.equal(stub.calls[0]?.action, 'send_group_msg')
    assert.deepEqual((stub.calls[0]?.body as { group_id: number }).group_id, 782795932)
  } finally {
    await stub.close()
  }
})

test('carries the access token as a bearer header', async () => {
  const stub = await startStub(() => ({ payload: { status: 'ok', retcode: 0, data: {} } }))
  try {
    await clientFor(stub.url, 'secret-token').sendGroup('1', [])
    assert.equal(stub.calls[0]?.authorization, 'Bearer secret-token')
  } finally {
    await stub.close()
  }
})

test('raises when NapCat reports a failed status', async () => {
  const stub = await startStub(() => ({ payload: { status: 'failed', retcode: 100, message: 'no such group' } }))
  try {
    await assert.rejects(clientFor(stub.url).sendGroup('1', []), (error: unknown) => {
      assert.ok(error instanceof OneBotActionError)
      assert.equal(error.retcode, 100)
      assert.match(error.message, /no such group/)
      return true
    })
  } finally {
    await stub.close()
  }
})

test('raises when NapCat reports a non-zero retcode without a status', async () => {
  const stub = await startStub(() => ({ payload: { retcode: 1200, wording: 'bad request' } }))
  try {
    await assert.rejects(clientFor(stub.url).sendGroup('1', []), /bad request/)
  } finally {
    await stub.close()
  }
})

test('raises when the transport answers with an HTTP error', async () => {
  const stub = await startStub(() => ({ status: 500, payload: { error: 'boom' } }))
  try {
    await assert.rejects(clientFor(stub.url).sendGroup('1', []), /HTTP 500/)
  } finally {
    await stub.close()
  }
})

test('raises when the body is not JSON', async () => {
  const server = createServer((_request, response) => {
    response.statusCode = 200
    response.end('not json')
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address() as AddressInfo
  try {
    await assert.rejects(
      clientFor(`http://127.0.0.1:${address.port}`).sendGroup('1', []),
      /body that is not JSON/,
    )
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close(error => (error === undefined ? resolve() : reject(error)))
    })
  }
})

test('reads the login identity of the account', async () => {
  const stub = await startStub(() => ({
    payload: { status: 'ok', retcode: 0, data: { user_id: 3916750998, nickname: 'Ada' } },
  }))
  try {
    const info = await clientFor(stub.url).getLoginInfo()
    assert.equal(info?.user_id, 3916750998)
    assert.equal(stub.calls[0]?.action, 'get_login_info')
  } finally {
    await stub.close()
  }
})

test('returns an empty member list when NapCat answers with something else', async () => {
  const stub = await startStub(() => ({ payload: { status: 'ok', retcode: 0, data: null } }))
  try {
    assert.deepEqual(await clientFor(stub.url).getGroupMembers('1'), [])
  } finally {
    await stub.close()
  }
})

test('reads the segments of a message that carries an array', () => {
  const segments = segmentsOf({
    post_type: 'message',
    message_type: 'group',
    message: [{ type: 'text', data: { text: 'hi' } }],
  })
  assert.deepEqual(segments, [{ type: 'text', data: { text: 'hi' } }])
})

test('reads the segments of a message that carries a string', () => {
  const segments = segmentsOf({
    post_type: 'message',
    message_type: 'private',
    message: 'plain',
  })
  assert.deepEqual(segments, [{ type: 'text', data: { text: 'plain' } }])
})

test('returns no segment for a message without a body', () => {
  assert.deepEqual(segmentsOf({ post_type: 'message', message_type: 'private' }), [])
})

test('is not connected before it starts', () => {
  assert.equal(clientFor('http://127.0.0.1:1').connected, false)
})
