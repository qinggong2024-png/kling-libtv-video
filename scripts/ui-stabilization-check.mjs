import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'
import { createPageResponses } from './fixtures/ui-page-responses.mjs'

const root = fileURLToPath(new URL('..', import.meta.url))
assert(process.env.PLAYWRIGHT_MODULE && process.env.UI_STABILIZATION_REPORT_DIR && process.env.UI_STUDIO_MEDIA_DIR)
const reportDir = resolve(process.env.UI_STABILIZATION_REPORT_DIR)
const outside = relative(root, reportDir)
assert(outside.startsWith('..') || isAbsolute(outside), 'Evidence stays outside the checkout')
const libraryView = process.env.UI_STABILIZATION_LIBRARY_VIEW ?? 'generated-assets'
assert(['generated-assets', 'catalog'].includes(libraryView), 'Specify the actual library implementation')
await mkdir(reportDir, { recursive: true })
const media = await readFile(resolve(process.env.UI_STUDIO_MEDIA_DIR, 'fixture-product.png'))
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'cache'), media })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const browser = await chromium.launch({ channel: process.env.UI_BROWSER_CHANNEL || 'chrome', headless: true })
const report = {
  scope: 'sprint8-p0-offline-no-provider', libraryView, capturedAt: new Date().toISOString(),
  browserVersion: browser.version(), cases: [], sourceHashes: {}, externalRequests: [], writes: [],
}
for (const file of [
  'frontend/src/api.ts', 'frontend/src/types.ts', 'frontend/src/app/App.tsx',
  'frontend/src/app/useAppNavigation.ts', 'frontend/src/styles.css',
  libraryView === 'generated-assets'
    ? 'frontend/src/features/library/GeneratedAssetsView.tsx'
    : 'frontend/src/features/library/ContentLibraryView.tsx',
  'scripts/ui-stabilization-check.mjs',
]) {
  report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')
}
const baseTask = createPageResponses().get('/api/v1/tasks')[1]
const quota = {
  currency: 'USD', business_date: '2026-10-14', accounting_version: 'USD_V1',
  total: '50.000', available: '0.001', reserved: '1.000', settled: '47.999', unknown: '1.000',
  request_max: '5.000', batch_max: '10.000', legacy_reconciliation_required: false,
  diagnostics: { pricing_configured: true }, enforced_entries: ['task_analysis'], deferred_entries: ['director_planning'],
}
let quotaStatus = 200
try {
  for (const [width, height] of [[1440, 900], [1024, 768]]) {
    fixture.state.tasks = Array.from({ length: 25 }, (_, index) => ({
      ...structuredClone(baseTask), id: `stabilization-task-${index}`, title: `Stabilization product ${index}`,
      variants: baseTask.variants.map((variant, variantIndex) => ({ ...variant, id: `stabilization-variant-${index}-${variantIndex}` })),
    }))
    fixture.state.phase = 'GENERATING'
    const context = await browser.newContext({ viewport: { width, height }, serviceWorkers: 'block' })
    const page = await context.newPage()
    page.setDefaultTimeout(12000)
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await context.route('**/*', route => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.origin !== fixture.origin && !['blob:', 'data:'].includes(url.protocol)) {
        report.externalRequests.push(url.origin)
        return route.abort()
      }
      if (!['GET', 'HEAD'].includes(request.method())) {
        report.writes.push({ path: url.pathname, method: request.method() })
        return route.abort()
      }
      if (url.pathname === '/api/v1/ai-usage/quota') return route.fulfill({
        status: quotaStatus,
        json: quotaStatus === 200 ? quota : { detail: { code: quotaStatus === 401 ? 'AUTH_REQUIRED' : 'AI_PRICE_NOT_CONFIGURED', message: 'Synthetic quota error' } },
      })
      return route.continue()
    })
    const result = { width, height, checks: 0, passed: false, restores: [] }
    const check = (condition, message) => { assert(condition, message); result.checks += 1 }
    const scrollState = () => page.evaluate(() => ({
      y: scrollY, max: document.documentElement.scrollHeight - innerHeight,
      url: location.href, returnSnapshot: sessionStorage.getItem('app.records-return'),
    }))
    const restore = async (expected, label) => {
      await page.locator('.foundation-drawer').waitFor({ state: 'hidden' })
      await page.locator('.task-table-row').nth(20).waitFor()
      await page.waitForFunction(y => Math.abs(scrollY - y) < 4, expected, { timeout: 12000 })
      check(new URL(page.url()).searchParams.get('q') === 'Stabilization', `${label}: search survives`)
      check(new URL(page.url()).searchParams.get('filter') === 'active', `${label}: filter survives`)
      check(await page.getByRole('textbox', { name: '搜索任务名称', exact: true }).inputValue() === 'Stabilization', `${label}: restored search matches URL`)
      result.restores.push({ label, expected, actual: (await scrollState()).y })
    }
    try {
      await page.goto(`${fixture.origin}/?view=records&filter=active&q=Stabilization`)
      await page.locator('.task-table-row').nth(20).waitFor()
      await page.locator('.video-studio').waitFor({ state: 'attached' })
      await page.locator('.page-loading').waitFor({ state: 'hidden' })
      for (const [status, code] of [[200, null], [503, 'AI_PRICE_NOT_CONFIGURED'], [401, 'AUTH_REQUIRED']]) {
        quotaStatus = status
        const response = await page.evaluate(async () => {
          const { getAIQuota } = await import('/src/api.ts')
          try { return { value: await getAIQuota() } }
          catch (error) { return { status: error.status, code: error.code } }
        })
        if (code === null) check(response.value.available === '0.001' && response.value.unknown === '1.000', 'Quota dollar strings and UNKNOWN survive')
        else check(response.status === status && response.code === code && !response.value, 'Quota errors do not become successful balances')
      }
      quotaStatus = 200
      for (const action of ['escape', 'back', 'reload-close']) {
        const row = page.locator('.task-table-row').nth(20)
        await row.scrollIntoViewIfNeeded()
        // Establish an exact position without inheriting the document's smooth-scroll animation.
        await page.evaluate(() => scrollTo({ top: scrollY, behavior: 'instant' }))
        const before = await scrollState()
        const expected = before.y
        result.pendingRestore = { action, expected, max: before.max }
        check(expected > 100, 'Scroll restoration covers a meaningful list position')
        await row.click()
        await page.locator('.foundation-drawer').waitFor({ state: 'visible' })
        const snapshot = await page.evaluate(() => JSON.parse(sessionStorage.getItem('app.records-return')))
        check(Math.abs(snapshot.scrollY - expected) < 4, 'Opening detail captures the actual list position')
        if (action === 'back') await page.goBack()
        else {
          if (action === 'reload-close') {
            await page.reload()
            await page.locator('.foundation-drawer').waitFor({ state: 'visible' })
          }
          await page.keyboard.press('Escape')
        }
        await restore(expected, action)
        delete result.pendingRestore
      }
      await page.screenshot({ path: resolve(reportDir, `records-restored-${width}.png`) })
      fixture.state.phase = 'DELIVERABLE'
      await page.goto(`${fixture.origin}/?view=library&pane=assets`)
      if (libraryView === 'generated-assets') {
        await page.locator('.generated-assets-view').waitFor()
        check(await page.getByRole('heading', { name: '生成资产', exact: true }).isVisible(), 'Generated library has its own heading')
        await page.locator('.generated-assets-results .result-card').nth(20).waitFor()
        await page.locator('.video-studio').waitFor({ state: 'attached' })
        await page.locator('.page-loading').waitFor({ state: 'hidden' })
        const detailButton = page.locator('.generated-assets-results .result-card').nth(20).getByRole('button', { name: '查看任务详情', exact: true })
        await detailButton.scrollIntoViewIfNeeded()
        await page.evaluate(() => scrollTo({ top: scrollY, behavior: 'instant' }))
        const libraryScroll = (await scrollState()).y
        check(libraryScroll > 100, 'Library return covers a meaningful result position')
        await detailButton.click()
        await page.locator('.foundation-drawer').waitFor({ state: 'visible' })
        await page.keyboard.press('Escape')
        await page.locator('.generated-assets-view').waitFor()
        check(new URL(page.url()).searchParams.get('view') === 'library', 'Asset detail returns to its source library')
        await page.waitForFunction(y => Math.abs(scrollY - y) < 4, libraryScroll)
        result.restores.push({ label: 'library-close', expected: libraryScroll, actual: (await scrollState()).y })
      } else {
        const library = page.locator('.content-library-view')
        await library.waitFor()
        check(await library.getByRole('heading', { name: '内容与主体库', exact: true }).isVisible(), 'Production retains its existing catalog')
        await library.getByRole('tab', { name: /风格库/ }).click()
        await library.getByRole('textbox', { name: '搜索风格库', exact: true }).fill('unmatched-stabilization-query')
        await library.getByText('没有匹配内容', { exact: true }).waitFor()
        await library.getByRole('button', { name: '清除内容库搜索关键词', exact: true }).click()
        await library.locator('.style-library-grid').waitFor()
        check(await library.getByRole('tab', { name: /风格库/ }).getAttribute('aria-selected') === 'true', 'Clearing library search preserves the active tab')
      }
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Library has no horizontal overflow')
      await page.screenshot({ path: resolve(reportDir, `library-${width}.png`) })
      check(errors.length === 0, 'No unhandled browser errors')
      result.passed = true
    } catch (error) {
      result.error = error.stack
      result.failureState = await scrollState()
      await page.screenshot({ path: resolve(reportDir, `failure-${width}.png`), fullPage: true })
    } finally {
      report.cases.push(result)
      await context.close()
    }
  }
  assert.deepEqual(report.externalRequests, [])
  assert.deepEqual(report.writes, [])
  assert.deepEqual(fixture.state.writes, [])
} finally {
  await browser.close()
  await fixture.server.close()
  report.passed = report.cases.length === 2 && report.cases.every(result => result.passed)
  report.sourcesUnchanged = true
  for (const [file, hash] of Object.entries(report.sourceHashes)) {
    const finalHash = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')
    if (finalHash !== hash) report.sourcesUnchanged = false
  }
  report.passed &&= report.sourcesUnchanged
  await writeFile(resolve(reportDir, 'report.json'), JSON.stringify(report, null, 2))
}
console.log(JSON.stringify({ passed: report.passed, sourcesUnchanged: report.sourcesUnchanged, cases: report.cases, evidence: reportDir }, null, 2))
if (!report.passed) process.exitCode = 1
