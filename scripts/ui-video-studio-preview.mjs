import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
assert(process.env.STUDIO_PREVIEW_MEDIA_DIR, 'Set STUDIO_PREVIEW_MEDIA_DIR to the external acceptance evidence directory')
const mediaDir = resolve(process.env.STUDIO_PREVIEW_MEDIA_DIR)
const pathFromRoot = relative(root, mediaDir)
assert(pathFromRoot.startsWith('..') || isAbsolute(pathFromRoot), 'Preview evidence must be outside the checkout')
const fixture = await createStudioFixtureServer({
  cacheDir: resolve(mediaDir, 'preview-vite-cache'),
  port: Number(process.env.STUDIO_PREVIEW_PORT ?? 5187),
  media: await readFile(resolve(mediaDir, 'fixture-product.png')),
  autoProgress: true,
})
fixture.state.video = await readFile(resolve(mediaDir, 'fixture-result.webm'))
console.log(`Offline Video Studio preview: ${fixture.origin}/studio/video`)
console.log('Synthetic APIs only. No proxy, real provider, database, or environment file.')
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => {
  await fixture.server.close()
  process.exit(0)
})
