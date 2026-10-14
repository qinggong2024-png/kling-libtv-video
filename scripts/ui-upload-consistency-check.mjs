import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'

assert(process.env.PLAYWRIGHT_MODULE && process.env.UPLOAD_REPORT_DIR && process.env.UI_STUDIO_MEDIA_DIR)
const reportDir = resolve(process.env.UPLOAD_REPORT_DIR)
await mkdir(reportDir, { recursive: true })
const media = await readFile(resolve(process.env.UI_STUDIO_MEDIA_DIR, 'fixture-product.png'))
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'cache'), media })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const report = { scope: 'isolated-upload-consistency-no-paid-generation', browser: browser.version(), cases: [], hashes: {} }
for (const file of ['frontend/src/shared/components/studio/ImageUploadTrigger.tsx', 'frontend/src/shared/components/studio/imageUploadTrigger.css']) {
  report.hashes[file] = createHash('sha256').update(await readFile(file)).digest('hex')
}
try {
  for (const [width, height] of [[1440, 900], [1024, 768], [768, 1024], [390, 844]]) {
    let baseline
    for (const [name, url, section, input] of [
      ['director', '/?view=images&pane=director', '.director-intake-primary', '.director-intake-primary input[type=file]'],
      ['image', '/?view=images&pane=image', '.image-reference-upload', '#image-reference-files'],
      ['video', '/?view=make&pane=video', '.upload-panel--storyboard', '.upload-panel--storyboard input[type=file]'],
    ]) {
      const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce', serviceWorkers: 'block' })
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await context.route('**/*', route => {
        const url = new URL(route.request().url())
        return url.origin === fixture.origin || ['blob:', 'data:'].includes(url.protocol) ? route.continue() : route.abort()
      })
      try {
        await page.goto(fixture.origin + url)
        const trigger = page.locator(`${section} .studio-image-upload`).first()
        await trigger.waitFor()
        const style = await trigger.evaluate(el => {
          const s = getComputedStyle(el), icon = getComputedStyle(el.querySelector('.studio-image-upload__icon'))
          return { minHeight: s.minHeight, padding: s.padding, radius: s.borderRadius, border: s.border, background: s.backgroundColor, direction: s.flexDirection, justify: s.justifyContent, textAlign: s.textAlign, iconWidth: icon.width }
        })
        baseline ??= style
        assert.deepEqual(style, baseline, `${name}: shared upload style matches director`)
        assert.equal(style.minHeight, '72px')
        assert.equal(style.textAlign, 'left')
        await trigger.focus()
        const chooserPromise = page.waitForEvent('filechooser')
        await trigger.press('Enter')
        const chooser = await chooserPromise
        await chooser.setFiles({ name: 'fixture-product.png', mimeType: 'image/png', buffer: media })
        if (name === 'director') await page.locator('.director-upload img').waitFor()
        else await page.locator(`${section} img`).first().waitFor()
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
        assert.deepEqual(errors, [])
        await page.screenshot({ path: resolve(reportDir, `${name}-${width}.png`), fullPage: true })
        report.cases.push({ name, width, height, style, passed: true, input })
        console.log(`PASS ${name}-${width}`)
      } finally { await context.close() }
    }
  }
  assert.equal(fixture.state.writes.length, 0, 'Local image selection must not submit generation or upload requests')
  await writeFile(resolve(reportDir, 'result.json'), JSON.stringify(report, null, 2))
} finally { await browser.close(); await fixture.server.close() }
