// Isolated dual-repository transport fixture; FFmpeg substitutes for paid editing.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createServer } from 'node:http'
import { mkdir } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const [root, nasRoot, userId, ownerId] = process.argv.slice(2)
assert(process.env.CUTFLOW_SOURCE_ROOT && root && nasRoot && userId && ownerId)
const { bridgeTick, enqueueImport, importStatus, authenticateBridge } = await import(
  pathToFileURL(resolve(process.env.CUTFLOW_SOURCE_ROOT, 'lib/libtv-bridge.mjs')).href,
)
const { readJson, writeJsonAtomic } = await import(
  pathToFileURL(resolve(process.env.CUTFLOW_SOURCE_ROOT, 'lib/atomic-json.mjs')).href,
)
await mkdir(nasRoot, { recursive: true })
await writeJsonAtomic(resolve(root, 'data/users.json'), [{ id: ownerId, status: 'active' }])
const config = { nasRoot, token: 'isolated-test-token', maxBytes: 1024 * 1024 * 10, owners: { [userId]: { ownerId } } }
const server = createServer(async (request, response) => {
  try {
    assert(authenticateBridge(request.headers.authorization, config))
    const url = new URL(request.url, 'http://localhost')
    let result
    if (request.method === 'POST') {
      let raw = ''
      for await (const chunk of request) raw += chunk
      result = await enqueueImport(root, config, JSON.parse(raw))
      await bridgeTick(root, config)
    } else {
      const batches = await readJson(resolve(root, 'data/batches.json'), [])
      const batch = batches[0]
      if (batch?.status === 'uploading') {
        const source = resolve(root, batch.files[0].storagePath)
        const output = resolve(root, batch.files[0].storagePath, '../../output/edited.mp4')
        await mkdir(resolve(output, '..'), { recursive: true })
        execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', source, '-t', '0.8', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', output], { timeout: 30000 })
        batch.status = 'review'
        batch.files.push({ id: randomUUID(), kind: 'output', storagePath: output, qualityStatus: 'passed' })
        await writeJsonAtomic(resolve(root, 'data/batches.json'), batches)
        await bridgeTick(root, config)
      }
      result = await importStatus(root, config, url.pathname.split('/').at(-1), url.searchParams.get('userId'))
    }
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify(result))
  } catch {
    response.writeHead(500, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify({ error: 'FIXTURE_FAILURE' }))
  }
})
server.listen(0, '127.0.0.1', () => console.log(`http://127.0.0.1:${server.address().port}`))
