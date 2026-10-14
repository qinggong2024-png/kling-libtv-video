import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'
import { createPageResponses } from './fixtures/ui-page-responses.mjs'

assert(process.env.PLAYWRIGHT_MODULE && process.env.UI_CUTFLOW_REPORT_DIR, 'Set Playwright and external report directory')
const reportDir = resolve(process.env.UI_CUTFLOW_REPORT_DIR)
await mkdir(reportDir, { recursive: true })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const browser = await chromium.launch({ channel: process.env.UI_BROWSER_CHANNEL || 'chrome', headless: true })
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'vite-cache') })
fixture.state.phase = 'DELIVERABLE'
fixture.state.tasks = createPageResponses().get('/api/v1/tasks').filter(task => task.phase === 'DELIVERABLE')
const videoPath = resolve(reportDir, 'test-video.mp4')
execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x288:rate=10', '-t', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', videoPath])
const media = await readFile(videoPath)
const report = { scope: 'isolated-fixture-no-production-writes', cases: [], errors: [] }
try {
  for (const width of [390, 1280]) {
    const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 } })
    const page = await context.newPage()
    page.on('pageerror', error => report.errors.push(error.message))
    let enabled = false
    let role = 'ADMIN'
    let handoffs = []
    let submissions = 0
    await context.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/v1/system/status') {
        const response = await route.fetch()
        return route.fulfill({ response, json: { ...await response.json(), cutflowHandoffEnabled: enabled } })
      }
      if (url.pathname === '/api/v1/auth/me') {
        const response = await route.fetch()
        return route.fulfill({ response, json: { ...await response.json(), role } })
      }
      if (url.pathname === '/api/v1/fixture-media/product.png') {
        return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="288"><rect width="160" height="288" fill="#c8d9cb"/><path d="M55 45L35 70L45 105L58 95V205H105V95L116 105L130 70L108 45Z" fill="#fff"/></svg>' })
      }
      if (url.pathname === '/api/v1/cutflow-handoffs' && route.request().method() === 'GET') {
        return route.fulfill({ json: { enabled, handoffs } })
      }
      if (url.pathname === '/api/v1/cutflow-handoffs' && route.request().method() === 'POST') {
        submissions += 1
        assert.equal(route.request().headers()['x-csrf-token'], 'fixture-csrf')
        const input = route.request().postDataJSON()
        assert(input.taskId && input.variantId)
        handoffs = [{ id: 'test-handoff', handoffKey: 'handoff-isolated', sourceArtifactId: 'fixture-artifact',
          status: 'QUEUED', cutflowBatchId: null, cutflowEditorUrl: null, errorMessage: null, outputs: [] }]
        return route.fulfill({ status: 202, json: handoffs[0] })
      }
      if (url.pathname.endsWith('/retry')) {
        handoffs[0].status = 'QUEUED'
        handoffs[0].errorMessage = null
        return route.fulfill({ json: handoffs[0] })
      }
      if (url.pathname === '/api/v1/cutflow-handoffs/test-handoff/outputs/render-1') {
        return route.fulfill({ contentType: 'video/mp4', body: media })
      }
      return route.continue()
    })
    await page.goto(`${fixture.origin}/?view=records`)
    await page.locator('.result-card').first().waitFor()
    assert.equal(await page.getByRole('button', { name: '继续剪辑', exact: true }).count(), 0)
    enabled = true
    await page.reload()
    await page.getByRole('button', { name: '继续剪辑', exact: true }).first().click()
    await page.getByRole('button', { name: '发送到 Cutflow', exact: true }).first().click()
    await page.getByRole('button', { name: '等待传输', exact: true }).first().waitFor()
    assert.equal(submissions, 1)
    assert.equal(await page.getByRole('button', { name: '发送到 Cutflow', exact: true }).count(), 0)
    await page.reload()
    await page.getByRole('button', { name: '继续剪辑', exact: true }).first().click()
    await page.getByRole('button', { name: '等待传输', exact: true }).first().waitFor()
    handoffs[0].status = 'FAILED'; handoffs[0].errorMessage = '隔离测试：NAS 断线'
    await page.reload()
    await page.getByRole('button', { name: '继续剪辑', exact: true }).first().click()
    await page.getByRole('button', { name: '重试交接', exact: true }).first().click()
    await page.getByRole('button', { name: '等待传输', exact: true }).first().waitFor()
    handoffs[0].status = 'PENDING_REVIEW'
    handoffs[0].cutflowBatchId = '4b590b50-2d50-489c-903a-dbfbc1d91960'
    handoffs[0].cutflowEditorUrl = 'http://cutflow.invalid/'
    handoffs[0].outputs = [{ id: 'render-1', sha256: 'a'.repeat(64), reviewStatus: 'PENDING', durationSeconds: 1,
      mediaUrl: '/api/v1/cutflow-handoffs/test-handoff/outputs/render-1', createdAt: new Date().toISOString() }]
    await page.reload()
    await page.getByRole('button', { name: '继续剪辑', exact: true }).first().click()
    await page.getByRole('button', { name: '剪辑版本 1 · 待审核', exact: true }).first().waitFor()
    assert.equal(await page.getByRole('link', { name: '打开 Cutflow' }).first().getAttribute('rel'), 'noreferrer')
    await page.screenshot({ path: resolve(reportDir, `cutflow-${width}.png`), fullPage: true })
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    assert(!overflow, `overflow at ${width}`)
    await page.getByRole('button', { name: '剪辑版本 1 · 待审核', exact: true }).first().click()
    await page.locator('dialog video').evaluate(async video => {
      if (video.readyState < 2) await new Promise((resolve, reject) => { video.onloadeddata = resolve; video.onerror = reject })
    })
    await page.keyboard.press('Escape')
    await page.locator('dialog').waitFor({ state: 'detached' })
    assert(await page.getByRole('button', { name: '剪辑版本 1 · 待审核', exact: true }).first()
      .evaluate(button => button === document.activeElement), 'Preview focus must return to its trigger')
    role = 'AUDITOR'; handoffs = []
    await page.reload()
    await page.getByRole('button', { name: '继续剪辑', exact: true }).first().click()
    assert.equal(await page.getByRole('button', { name: '发送到 Cutflow', exact: true }).count(), 0)
    report.cases.push({ width, passed: true, checks: ['feature-gate', 'submit-once', 'reload', 'retry', 'pending-derivative', 'decode-preview', 'escape-focus', 'auditor-readonly', 'no-overflow'] })
    await context.close()
  }
  assert.deepEqual(report.errors, [])
} finally {
  await writeFile(resolve(reportDir, 'browser-report.json'), JSON.stringify(report, null, 2))
  await browser.close()
  await fixture.server.close()
}
console.log(JSON.stringify(report))
