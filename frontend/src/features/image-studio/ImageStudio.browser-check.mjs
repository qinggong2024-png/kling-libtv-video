import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from '../../../../scripts/fixtures/video-studio-server.mjs'

const root = resolve(fileURLToPath(new URL('../../../../', import.meta.url)))
assert(process.env.PLAYWRIGHT_MODULE && process.env.IMAGE_STUDIO_EVIDENCE_DIR && process.env.UI_STUDIO_MEDIA_DIR)
const reportDir = resolve(process.env.IMAGE_STUDIO_EVIDENCE_DIR)
await mkdir(reportDir, { recursive: true })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const media = await readFile(resolve(process.env.UI_STUDIO_MEDIA_DIR, 'fixture-product.png'))
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'vite-cache'), media })
const browser = await chromium.launch({ channel: process.env.UI_BROWSER_CHANNEL || 'chrome', headless: true })
const report = {
  scope: 'image-studio-ia-isolated',
  browserVersion: browser.version(),
  sourceHashes: {},
  cases: [],
  blockedExternalRequests: [],
}

for (const file of [
  'frontend/src/features/image-studio/ImageStudio.tsx',
  'frontend/src/features/image-studio/ImageStudioHome.tsx',
  'frontend/src/features/image-studio/ImageToImageStudio.tsx',
  'frontend/src/features/image-studio/TextToImageStudio.tsx',
  'frontend/src/features/image-studio/BatchStudio.tsx',
  'frontend/src/features/image-studio/ImageRecords.tsx',
  'frontend/src/features/image-studio/imageStudioNavigation.ts',
  'frontend/src/styles.css',
]) {
  report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')
}

try {
  for (const [width, height] of [[1440, 900], [1024, 768], [768, 1024], [390, 844], [320, 720]]) {
    const context = await browser.newContext({
      viewport: { width, height },
      reducedMotion: width === 390 ? 'reduce' : 'no-preference',
      serviceWorkers: 'block',
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const writes = []
    const batches = new Map()
    await context.route('**/*', async (route) => {
      const url = new URL(route.request().url())
      if (url.origin !== fixture.origin && !['blob:', 'data:'].includes(url.protocol)) {
        report.blockedExternalRequests.push(url.origin)
        return route.abort()
      }
      if (url.pathname === '/api/v1/image-generation-batches' && route.request().method() === 'POST') {
        const body = await new Response(route.request().postDataBuffer(), {
          headers: { 'content-type': route.request().headers()['content-type'] },
        }).formData()
        const manifest = JSON.parse(body.get('clientManifest'))
        writes.push({ manifest, fileCount: body.getAll('files').length, key: route.request().headers()['idempotency-key'] })
        const batch = {
          id: `fixture-image-batch-${writes.length}`, clientBatchId: manifest.clientBatchId, status: 'completed',
          items: manifest.items.map((item, i) => ({
            id: `fixture-item-${i}`, clientTaskId: item.clientTaskId, outfitId: item.outfitId,
            status: 'completed', providerTaskId: 'synthetic-task', providerTaskIds: ['synthetic-task'],
            modelId: 'offline-fixture', outputs: [], error: null,
          })),
        }
        batches.set(batch.id, batch)
        return route.fulfill({ json: batch })
      }
      if (url.pathname.startsWith('/api/v1/image-generation-batches/')) {
        return route.fulfill({ json: batches.get(url.pathname.split('/').at(-1)) })
      }
      return route.continue()
    })

    const name = `image-studio-ia-${width}`
    try {
      await page.goto(`${fixture.origin}/?view=images&pane=image`, { waitUntil: 'networkidle' })
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })
      assert.equal(await page.locator('.image-studio-entry').count(), 3)
      assert.deepEqual(
        await page.locator('.image-studio-entry strong').allTextContents(),
        ['图生图', '文生图', '批量生产'],
      )
      assert.equal(await page.getByRole('button', { name: /生图记录/ }).count(), 1)
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'home has no horizontal overflow')
      for (const entry of await page.locator('.image-studio-entry').all()) {
        const box = await entry.boundingBox()
        assert(box.y >= 0 && box.y + box.height <= height - (width <= 820 ? 64 : 0), `all entries visible in first viewport at ${width}`)
      }
      await page.screenshot({ path: resolve(reportDir, `${name}-home.png`), fullPage: true })

      await page.getByRole('button', { name: /图生图/ }).click()
      await page.getByRole('heading', { name: '图生图', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'image-to-image')
      assert.equal(await page.locator('.outfit-navigator').count(), 0, 'quick creation does not expose outfit management')
      const imageFile = { name: 'synthetic-reference.png', mimeType: 'image/png', buffer: media }
      await page.locator('#image-quick-product-files').setInputFiles(imageFile)
      await page.locator('#image-quick-person-files').setInputFiles(imageFile)
      await page.getByRole('textbox', { name: '提示词', exact: true }).fill('保留人物和环境，准确还原商品细节')
      await page.getByLabel('数量', { exact: true }).selectOption('2')
      await page.getByRole('button', { name: '生成图片', exact: true }).click()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      assert.equal(writes.length, 1)
      assert.equal(writes[0].manifest.items.length, 1)
      assert.deepEqual(writes[0].manifest.modes, ['fusion'])
      assert.equal(writes[0].manifest.items[0].prompts.fusion, '保留人物和环境，准确还原商品细节')
      assert.equal(writes[0].fileCount, 2)
      assert.equal(writes[0].key, writes[0].manifest.clientBatchId)
      await page.locator('.image-records-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.getByRole('button', { name: /图生图/ }).click()
      assert.equal(await page.getByRole('textbox', { name: '提示词', exact: true }).inputValue(), '保留人物和环境，准确还原商品细节')
      await page.locator('.image-quick-save').filter({ hasText: '草稿已保存' }).waitFor()
      await page.screenshot({ path: resolve(reportDir, `${name}-quick.png`), fullPage: true })
      await page.locator('.image-quick-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })

      await page.getByRole('button', { name: /文生图/ }).click()
      await page.getByRole('heading', { name: '文生图', exact: true }).waitFor()
      await page.getByRole('textbox', { name: '提示词', exact: true }).fill('生活方式广告创意草稿')
      await page.reload({ waitUntil: 'networkidle' })
      assert.equal(await page.getByRole('textbox', { name: '提示词', exact: true }).inputValue(), '生活方式广告创意草稿')
      assert(await page.getByRole('button', { name: '文生图暂未开放', exact: true }).isDisabled())
      await page.locator('.image-quick-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })

      await page.getByRole('button', { name: /批量生产/ }).click()
      await page.getByRole('heading', { name: '批量生产', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'batch')
      assert.equal(await page.locator('.image-center-create').count(), 0, 'production hub precedes complex editor')
      await page.getByRole('button', { name: /产品套装/ }).click()
      await page.getByRole('heading', { level: 1, name: '产品套装', exact: true }).waitFor()
      assert.equal(await page.locator('.generation-config').count(), 0)
      await page.getByRole('button', { name: '进入批量创作', exact: true }).click()
      await page.locator('.image-center-create').waitFor({ state: 'visible' })
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'batch-create')
      await page.getByRole('button', { name: '添加套装', exact: true }).click()
      const productFiles = page.locator('.active-outfit-editor input[type=file]')
      await productFiles.setInputFiles(imageFile)
      await page.getByRole('button', { name: '创建生图任务', exact: true }).click()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      assert.equal(writes.length, 2)
      assert.equal(writes[1].manifest.items.length, 2, 'batch still submits all ready outfits')
      await page.locator('.image-records-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.getByRole('button', { name: /批量生产/ }).click()
      await page.getByRole('button', { name: /分镜生产/ }).click()
      await page.getByRole('heading', { name: '分镜生产', exact: true }).waitFor()
      assert.equal(await page.getByRole('radio', { name: /分镜图生成/ }).getAttribute('aria-checked'), 'true')
      await page.getByRole('button', { name: '批量生产', exact: true }).click()
      await page.locator('.image-batch-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })

      await page.getByRole('button', { name: /生图记录/ }).click()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'records')
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'records has no horizontal overflow')
      await page.goBack()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), null)
      await page.goForward()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      await page.reload({ waitUntil: 'networkidle' })
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      const nav = page.getByRole('navigation', { name: width > 820 ? '制作导航' : '移动端主导航', exact: true })
      await nav.getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })
      await context.route('**/api/v1/system/status', route => route.fulfill({ status: 502, json: { detail: 'Synthetic gateway failure' } }))
      await page.goto(`${fixture.origin}/?view=images&pane=image&imageMode=image-to-image`, { waitUntil: 'networkidle' })
      await page.getByRole('heading', { name: '图生图', exact: true }).waitFor()
      assert(await page.getByRole('button', { name: '生成图片', exact: true }).isDisabled(), '502 blocks new submissions')
      assert.equal(writes.length, 2, 'service failure creates no new tasks')
      assert.deepEqual(errors, [])
      await page.screenshot({ path: resolve(reportDir, `${name}-unavailable.png`), fullPage: true })
      report.cases.push({ name, width, height, passed: true, submissions: writes })
    } catch (error) {
      console.error(`${name}: ${error.message}`)
      await page.screenshot({ path: resolve(reportDir, `${name}-failure.png`), fullPage: true })
      report.cases.push({ name, width, height, passed: false, error: error.stack, browserErrors: errors })
    } finally {
      await context.close()
    }
  }
} finally {
  await browser.close()
  await fixture.server.close()
  await writeFile(resolve(reportDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
}

console.log(JSON.stringify({
  cases: report.cases.map(({ name, width, passed, error }) => ({ name, width, passed, error })),
  evidence: reportDir,
}, null, 2))
if (report.cases.some((result) => !result.passed)) process.exitCode = 1
