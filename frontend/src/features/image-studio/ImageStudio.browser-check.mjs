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
  'frontend/src/features/image-studio/ImageStudioHeader.tsx',
  'frontend/src/features/image-studio/shared/ReferenceImageUpload.tsx',
  'frontend/src/features/image-studio/imageReferenceSequence.ts',
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
  for (const [width, height] of (process.env.IMAGE_STUDIO_DESKTOP_ONLY === '1'
    ? [[1440, 900], [1024, 768]]
    : [[1440, 900], [1024, 768], [768, 1024], [390, 844], [320, 720]])) {
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
        writes.push({ manifest, fileCount: body.getAll('files').length, fileNames: body.getAll('files').map(file => file.name), key: route.request().headers()['idempotency-key'] })
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
      await page.getByRole('heading', { name: '图生图', exact: true }).waitFor()
      const tabs = page.getByRole('tablist', { name: '图片创作模式' })
      assert.deepEqual(await tabs.getByRole('tab').allTextContents(), ['图生图', '文生图仅草稿', '批量生产'])
      assert.equal(await page.getByRole('tab', { name: '图生图', exact: true }).getAttribute('aria-selected'), 'true')
      assert.equal(await page.locator('.image-studio-entry').count(), 0)
      assert.equal(await page.getByRole('button', { name: /生图记录/ }).count(), 1)
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'direct creation has no horizontal overflow')
      for (const entry of await tabs.getByRole('tab').all()) {
        const box = await entry.boundingBox()
        assert(box.y >= 0 && box.y + box.height <= height - (width <= 820 ? 64 : 0), `all tabs visible in first viewport at ${width}`)
      }
      const upload = page.getByRole('region', { name: '参考图片', exact: true })
      const input = page.locator('#image-reference-files')
      const filenames = () => page.locator('.image-reference-tile__preview').evaluateAll(elements => elements.map(element => element.title))
      const saved = () => page.locator('.image-quick-save').filter({ hasText: '草稿已保存' }).waitFor()
      const imageFile = name => ({ name, mimeType: 'image/png', buffer: media })
      assert.equal(await page.locator('.image-quick-studio input[type=file]').count(), 1)
      assert.equal(await input.getAttribute('multiple'), '')
      assert.equal(await page.getByText('商品图', { exact: true }).count(), 0)
      assert.equal(await page.getByText('人物图', { exact: true }).count(), 0)
      assert(await page.getByRole('button', { name: '生成图片', exact: true }).isDisabled())
      await page.screenshot({ path: resolve(reportDir, `${name}-initial.png`), fullPage: true })
      assert.equal(await page.locator('.outfit-navigator').count(), 0, 'quick creation does not expose outfit management')
      await page.locator('.image-simple-advanced summary').click()
      await page.getByLabel('模型', { exact: true }).selectOption('gpt')
      await input.setInputFiles([imageFile('a.png'), imageFile('b.png'), imageFile('c.png')])
      await page.locator('.image-reference-tile').nth(0).dragTo(page.locator('.image-reference-tile').nth(1))
      assert.deepEqual(await filenames(), ['b.png', 'a.png', 'c.png'], 'native dragging updates the displayed sequence')
      await page.getByRole('button', { name: '后移参考图 2', exact: true }).focus()
      await page.keyboard.press('Enter')
      assert.deepEqual(await filenames(), ['b.png', 'c.png', 'a.png'], 'native dragging updates the displayed sequence')
      await page.getByRole('button', { name: '前移参考图 3', exact: true }).click()
      assert.deepEqual(await filenames(), ['b.png', 'a.png', 'c.png'], 'move controls support keyboard and touch')
      await page.getByRole('button', { name: '删除参考图 2', exact: true }).click()
      await input.setInputFiles([imageFile('d.png'), imageFile('e.png'), imageFile('f.png'), imageFile('g.png'), imageFile('overflow.png')])
      assert.deepEqual(await filenames(), ['b.png', 'c.png', 'd.png', 'e.png', 'f.png', 'g.png'])
      await upload.getByText(/超出的图片未添加/).waitFor()
      await page.getByLabel('模型', { exact: true }).selectOption('nanobanana')
      assert.deepEqual(await filenames(), ['b.png', 'c.png', 'd.png', 'e.png', 'f.png', 'g.png'], 'changing model never discards references')
      assert(await page.getByRole('button', { name: '生成图片', exact: true }).isDisabled())
      await page.getByText('当前模型最多支持 4 张参考图，请减少图片或切换模型。', { exact: true }).waitFor()
      await page.getByRole('button', { name: '删除参考图 6', exact: true }).click()
      await page.getByRole('button', { name: '删除参考图 5', exact: true }).click()
      await page.getByRole('button', { name: '删除参考图 4', exact: true }).click()
      await input.setInputFiles({ name: 'unsupported.txt', mimeType: 'text/plain', buffer: Buffer.from('fixture') })
      await upload.getByText(/仅支持 JPG/).waitFor()
      assert.deepEqual(await filenames(), ['b.png', 'c.png', 'd.png'])
      await input.setInputFiles(imageFile('e.png'))
      await page.getByRole('textbox', { name: '提示词', exact: true }).fill('保留人物和环境，准确还原商品细节')
      await page.getByLabel('数量', { exact: true }).selectOption('2')
      await saved()
      await page.reload({ waitUntil: 'networkidle' })
      await page.getByRole('heading', { name: '图生图', exact: true }).waitFor()
      assert.deepEqual(await filenames(), ['b.png', 'c.png', 'd.png', 'e.png'], 'IndexedDB restores reordered files')
      await page.screenshot({ path: resolve(reportDir, `${name}-quick.png`), fullPage: true })
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'uploaded tiles have no overflow')
      await page.getByRole('button', { name: '生成图片', exact: true }).click()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      assert.equal(writes.length, 1)
      assert.equal(writes[0].manifest.items.length, 1)
      assert.deepEqual(writes[0].manifest.modes, ['fusion'])
      assert.equal(writes[0].manifest.items[0].prompts.fusion, '保留人物和环境，准确还原商品细节')
      assert.equal(writes[0].fileCount, 4)
      assert.deepEqual(writes[0].fileNames, ['b.png', 'c.png', 'd.png', 'e.png'], 'multipart preserves user order')
      assert.deepEqual(writes[0].manifest.items[0].referenceRoles, [
        { role: 'model.front', fileIndex: 0 }, { role: 'product.front', fileIndex: 1 },
        { role: 'product.back', fileIndex: 2 }, { role: 'model.back', fileIndex: 3 },
      ])
      assert.equal(writes[0].manifest.expectedGenerationCount, 4, 'count includes existing front/back generation')
      assert.equal(writes[0].key, writes[0].manifest.clientBatchId)
      await page.locator('.image-records-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      assert.equal(await page.getByRole('textbox', { name: '提示词', exact: true }).inputValue(), '保留人物和环境，准确还原商品细节')
      await page.getByRole('tab', { name: '图生图', exact: true }).focus()
      await page.keyboard.press('ArrowRight')
      await page.getByRole('heading', { name: '文生图', exact: true }).waitFor()
      await page.getByRole('textbox', { name: '提示词', exact: true }).fill('生活方式广告创意草稿')
      await page.reload({ waitUntil: 'networkidle' })
      assert.equal(await page.getByRole('textbox', { name: '提示词', exact: true }).inputValue(), '生活方式广告创意草稿')
      assert(await page.getByRole('button', { name: '文生图暂未开放', exact: true }).isDisabled())
      await page.getByRole('tab', { name: '批量生产', exact: true }).click()
      await page.getByRole('heading', { name: '批量创作', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'batch-create')
      await page.locator('.image-center-create').waitFor({ state: 'visible' })
      await page.getByRole('navigation', { name: '批量生产', exact: true }).getByRole('button', { name: '产品套装', exact: true }).click()
      await page.getByRole('heading', { level: 2, name: '产品套装', exact: true }).waitFor()
      assert.equal(await page.locator('.generation-config').count(), 0)
      await page.getByRole('button', { name: '批量创作', exact: true }).click()
      await page.locator('.image-center-create').waitFor({ state: 'visible' })
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'batch-create')
      await page.getByRole('button', { name: '添加套装', exact: true }).click()
      const productFiles = page.locator('.active-outfit-editor input[type=file]')
      await productFiles.setInputFiles(imageFile('batch-product.png'))
      await page.getByRole('button', { name: '创建生图任务', exact: true }).click()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      assert.equal(writes.length, 2)
      assert.equal(writes[1].manifest.items.length, 2, 'batch still submits all ready outfits')
      await page.locator('.image-records-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.getByRole('tab', { name: '批量生产', exact: true }).click()
      await page.getByRole('button', { name: /分镜生产/ }).click()
      await page.getByRole('heading', { name: '分镜生产', exact: true }).waitFor()
      assert.equal(await page.getByRole('radio', { name: /分镜图生成/ }).getAttribute('aria-checked'), 'true')
      await page.getByRole('tab', { name: '图生图', exact: true }).click()
      assert.equal(await page.locator('.image-center-command-bar').count(), 0, 'batch command bar leaves with its tab')
      await saved()
      await page.getByRole('button', { name: /生图记录/ }).click()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'records')
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'records has no horizontal overflow')
      await page.goBack()
      await page.getByRole('heading', { name: '图生图', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), null)
      await page.goForward()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      await page.reload({ waitUntil: 'networkidle' })
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      const nav = page.getByRole('navigation', { name: width > 820 ? '制作导航' : '移动端主导航', exact: true })
      await nav.getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.getByRole('heading', { name: '图生图', exact: true }).waitFor()
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
