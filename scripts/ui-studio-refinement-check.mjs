import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
assert(process.env.PLAYWRIGHT_MODULE && process.env.UI_REFINEMENT_REPORT_DIR && process.env.UI_STUDIO_MEDIA_DIR)
const reportDir = resolve(process.env.UI_REFINEMENT_REPORT_DIR)
assert(relative(root, reportDir).startsWith('..') || isAbsolute(relative(root, reportDir)), 'Evidence must be external')
await mkdir(reportDir, { recursive: true })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const media = await readFile(resolve(process.env.UI_STUDIO_MEDIA_DIR, 'fixture-product.png'))
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'vite-cache'), media })
const browser = await chromium.launch({ channel: process.env.UI_BROWSER_CHANNEL || 'msedge', headless: true })
const report = { scope: 'isolated-refinement-no-provider', browserVersion: browser.version(), cases: [], externalRequests: [], sourceHashes: {} }
for (const file of ['frontend/src/app/AppShell.tsx', 'frontend/src/CustomPromptField.tsx', 'frontend/src/styles.css', 'frontend/src/features/production/studioRefinement.css', 'frontend/src/features/production/ProductionComposer.tsx', 'frontend/src/shared/components/ui/Modal.tsx', 'frontend/src/shared/components/ui/Button.tsx', 'scripts/ui-studio-refinement-check.mjs']) {
  report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')
}
const contrast = (fg, bg) => {
  const light = (color) => color.match(/\d+/g).slice(0, 3).map(Number).map(n => n / 255).map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4).reduce((sum, n, i) => sum + n * [.2126, .7152, .0722][i], 0)
  const [a, b] = [light(fg), light(bg)].sort((a, b) => b - a)
  return (a + .05) / (b + .05)
}
try {
  for (const width of [1440, 390]) for (const motion of ['no-preference', 'reduce']) {
    fixture.state.tasks = []; fixture.state.writes = []; fixture.state.unexpected = []
    const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, reducedMotion: motion, serviceWorkers: 'block' })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const result = { width, motion, passed: false }
    let presetAttempts = 0
    await context.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.origin !== fixture.origin && !['blob:', 'data:'].includes(url.protocol)) {
        report.externalRequests.push(url.origin); return route.abort()
      }
      if (url.pathname === '/api/v1/video-templates') await new Promise(resolve => setTimeout(resolve, 1000))
      if (url.pathname === '/api/v1/uploads' && route.request().method() === 'POST') await new Promise(resolve => setTimeout(resolve, 500))
      if (url.pathname === '/api/v1/prompt-presets' && route.request().method() === 'POST') {
        presetAttempts += 1
        await new Promise(resolve => setTimeout(resolve, 400))
        return route.fulfill({ status: presetAttempts === 1 ? 503 : 201, json: presetAttempts === 1
          ? { detail: '离线合成：保存暂不可用' }
          : { id: 'fixture-preset', ...route.request().postDataJSON(), createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() } })
      }
      return route.continue()
    })
    try {
      await page.goto(`${fixture.origin}/studio/video`)
      await page.getByRole('combobox', { name: '视频模板', exact: true }).waitFor()
      assert(await page.getByRole('button', { name: '开始生成', exact: true }).isDisabled())
      await page.screenshot({ path: resolve(reportDir, `loading-${width}-${motion}.png`) })
      await page.getByRole('combobox', { name: '视频模板', exact: true }).getByRole('option', { name: '服装多镜头展示', exact: true }).waitFor({ state: 'attached' })
      if (width === 1440) assert.equal(await page.locator('.sidebar').evaluate(el => Math.round(el.getBoundingClientRect().width)), 240)
      const helper = await page.locator('.composer-submit-summary small').evaluate(el => ({ fg: getComputedStyle(el).color, bg: getComputedStyle(el.closest('.app-shell')).backgroundColor }))
      result.paymentContrast = contrast(helper.fg, helper.bg)
      assert(result.paymentContrast >= 4.5)
      for (const control of await page.locator('.composer-result-count .segmented-control label, .composer-duration-field select').all()) {
        const bounds = await control.boundingBox()
        assert(bounds && bounds.width >= 44 && bounds.height >= 44, 'Footer controls have 44px touch targets')
      }
      await page.locator('.upload-panel input[type=file]').first().setInputFiles({ name: 'product.png', mimeType: 'image/png', buffer: media })
      const upload = page.locator('.upload-panel--storyboard')
      await upload.dispatchEvent('dragenter')
      assert((await upload.getAttribute('class')).includes('is-drop-target'))
      await upload.dispatchEvent('dragleave')
      assert(!(await upload.getAttribute('class')).includes('is-drop-target'))
      await page.getByRole('radio', { name: '自定义提示词', exact: true }).click()
      await page.getByPlaceholder('输入画面动作、镜头和节奏要求').fill('保持完整服装轮廓，缓慢转身。')
      const save = page.getByRole('button', { name: '保存当前方案', exact: true })
      await save.click()
      const dialog = page.getByRole('dialog', { name: '保存为新方案' })
      await dialog.waitFor()
      await dialog.getByLabel('方案名称', { exact: true }).fill('服装展示')
      await dialog.getByRole('button', { name: '保存', exact: true }).click()
      await page.keyboard.press('Escape')
      assert(await dialog.isVisible(), 'Busy save preserves the original dismiss guard')
      await dialog.getByRole('alert').waitFor()
      await page.screenshot({ path: resolve(reportDir, `preset-error-${width}-${motion}.png`) })
      await dialog.getByRole('button', { name: '保存', exact: true }).click()
      await dialog.waitFor({ state: 'hidden' })
      await page.getByText('已载入：服装展示', { exact: true }).waitFor()
      assert(await save.evaluate(el => el === document.activeElement))
      assert.equal(presetAttempts, 2)
      await page.getByRole('radio', { name: '自动化生成', exact: true }).click()
      const generate = page.getByRole('button', { name: '开始生成', exact: true })
      await generate.click()
      const progress = page.getByRole('progressbar')
      await progress.waitFor()
      assert.equal(await page.getByRole('button', { name: '正在准备素材', exact: true }).getAttribute('aria-busy'), 'true')
      const progressStyle = await progress.locator('span').evaluate(el => ({ width: getComputedStyle(el).width, duration: getComputedStyle(el).transitionDuration, origin: getComputedStyle(el).transformOrigin }))
      if (motion === 'reduce') assert.equal(progressStyle.duration, '0s')
      await page.screenshot({ path: resolve(reportDir, `upload-${width}-${motion}.png`) })
      await page.locator('.studio-task-card').waitFor()
      await page.getByRole('status').filter({ hasText: '已进入' }).waitFor()
      await page.screenshot({ path: resolve(reportDir, `submitted-${width}-${motion}.png`) })
      assert.equal(fixture.state.writes.filter(write => write.path === '/api/v1/video-tasks').length, 1)
      // Half the desktop CSS viewport approximates desktop browser 200% reflow.
      // CSS zoom does not update media queries; it is not a valid substitute for browser zoom.
      if (width === 1440) {
        await page.setViewportSize({ width: 720, height: 450 })
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '720px desktop reflow has no page overflow')
        await page.screenshot({ path: resolve(reportDir, `reflow-720-${motion}.png`) })
        result.desktopZoomEquivalentViewport = '720x450'
      }
      assert.deepEqual(errors, [])
      assert.deepEqual(fixture.state.unexpected, [])
      result.passed = true
    } catch (error) {
      result.failure = error.message
      await page.screenshot({ path: resolve(reportDir, `failure-${width}-${motion}.png`) }).catch(() => {})
    } finally {
      report.cases.push(result)
      await context.close()
      console.log(`${result.passed ? 'PASS' : 'FAIL'} refinement-${width}-${motion}${result.failure ? `: ${result.failure}` : ''}`)
    }
  }
  report.passed = report.cases.every(item => item.passed) && !report.externalRequests.length
  await writeFile(resolve(reportDir, 'result.json'), JSON.stringify(report, null, 2))
  assert(report.passed, 'Refinement acceptance failed')
} finally {
  await browser.close()
  await fixture.server.close()
}
