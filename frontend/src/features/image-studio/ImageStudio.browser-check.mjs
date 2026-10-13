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
  for (const [width, height] of [[1440, 900], [1024, 768], [768, 1024], [390, 844]]) {
    const context = await browser.newContext({
      viewport: { width, height },
      reducedMotion: width === 390 ? 'reduce' : 'no-preference',
      serviceWorkers: 'block',
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await context.route('**/*', (route) => {
      const url = new URL(route.request().url())
      if (url.origin !== fixture.origin && !['blob:', 'data:'].includes(url.protocol)) {
        report.blockedExternalRequests.push(url.origin)
        return route.abort()
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

      await page.getByRole('button', { name: /图生图/ }).click()
      await page.getByRole('heading', { name: '图生图', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'image-to-image')
      await page.locator('.image-quick-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })

      await page.getByRole('button', { name: /文生图/ }).click()
      await page.getByRole('heading', { name: '文生图', exact: true }).waitFor()
      assert.equal(await page.getByRole('textbox', { name: '你想先探索什么？' }).count(), 1)
      await page.locator('.image-quick-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })

      await page.getByRole('button', { name: /批量生产/ }).click()
      await page.getByRole('heading', { name: '批量生产', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'batch')
      await page.locator('.image-center-create').waitFor({ state: 'visible' })
      await page.locator('.image-batch-studio').getByRole('button', { name: '图片工作室', exact: true }).click()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })

      await page.getByRole('button', { name: /生图记录/ }).click()
      await page.getByRole('heading', { name: '生图记录', exact: true }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), 'records')
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'records has no horizontal overflow')
      await page.goBack()
      await page.locator('.image-studio-home').waitFor({ state: 'visible' })
      assert.equal(new URL(page.url()).searchParams.get('imageMode'), null)
      assert.deepEqual(errors, [])
      await page.screenshot({ path: resolve(reportDir, `${name}.png`), fullPage: true })
      report.cases.push({ name, width, height, passed: true })
    } catch (error) {
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
