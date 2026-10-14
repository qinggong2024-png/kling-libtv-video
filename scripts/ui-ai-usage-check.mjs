import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'
import { collectPageSnapshot, isPageReady, ROUTES } from './ui-smoke.mjs'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
assert(process.env.PLAYWRIGHT_MODULE, 'Set PLAYWRIGHT_MODULE to an existing installed package; no install is performed')
assert(process.env.UI_AI_USAGE_REPORT_DIR, 'Set UI_AI_USAGE_REPORT_DIR to an absolute directory outside the checkout')
assert(isAbsolute(process.env.UI_AI_USAGE_REPORT_DIR), 'Evidence path must be absolute')
const reportDir = resolve(process.env.UI_AI_USAGE_REPORT_DIR)
const outside = relative(root, reportDir)
assert(outside.startsWith('..') || isAbsolute(outside), 'Evidence must remain outside the checkout')
await mkdir(reportDir, { recursive: true })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const report = {
  scope: 'offline-settings-dollar-budget-only',
  capturedAt: new Date().toISOString(),
  sourceHead: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
  sourceHashes: {}, browserVersion: null, cases: [],
  safety: { externalRequests: [], writeRequests: [], unmatchedRequests: [] },
}
for (const file of [
  'frontend/src/api.ts', 'frontend/src/types.ts', 'frontend/src/features/settings/SettingsView.tsx',
  'frontend/src/features/settings/AIDailyBudget.tsx', 'frontend/src/features/settings/aiDailyBudget.css',
  'scripts/ui-ai-usage-check.mjs', 'scripts/fixtures/video-studio-server.mjs',
]) {
  report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')
}

const baseQuota = {
  currency: 'USD', business_date: '2026-10-14', accounting_version: 'USD_V1',
  total: '50.000', available: '39.000', reserved: '3.000', settled: '6.000', unknown: '2.000',
  request_max: '5.000', batch_max: '10.000', legacy_reconciliation_required: false,
  diagnostics: { total_units: 50000, available_units: 39000 },
  enforced_entries: ['task_analysis', 'prompt_assistant'],
  deferred_entries: ['image_submission', 'video_submission', 'feedback_learning', 'director_planning', 'quality_review'],
}
const scenarios = ['normal', 'failure-retry', 'low-available', 'cross-day-unknown', 'unconfigured-prices', 'legacy-reconciliation', 'unauthorized']
let browser
let fixture

async function checkLayout(page, section) {
  assert(await section.isVisible())
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Page has horizontal overflow')
  assert(await section.evaluate((node) => {
    const bounds = node.getBoundingClientRect()
    return bounds.left >= 0 && bounds.right <= innerWidth + 1 && node.scrollWidth <= node.clientWidth + 1
  }), 'Budget section overflows its available width')
  assert(await section.locator('dt, dd, .ai-budget-categories span').evaluateAll((nodes) => nodes.every((node) => {
    const child = node.getBoundingClientRect()
    const parent = node.parentElement.getBoundingClientRect()
    return child.left >= parent.left - 1 && child.right <= parent.right + 1
  })), 'Budget text overlaps adjacent cells')
  const style = await section.evaluate((node) => {
    const value = getComputedStyle(node)
    return { position: value.position, shadow: value.boxShadow, radius: value.borderRadius }
  })
  assert.equal(style.shadow, 'none')
  assert.equal(style.radius, '0px')
  assert(!['fixed', 'absolute', 'sticky'].includes(style.position))
}

async function run(width, height, scenario) {
  const result = { width, height, scenario, passed: false, screenshots: [] }
  report.cases.push(result)
  const context = await browser.newContext({
    viewport: { width, height }, reducedMotion: 'reduce', serviceWorkers: 'block',
  })
  const page = await context.newPage()
  page.setDefaultTimeout(12000)
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  let requestCount = 0
  let failRefresh = false
  let release
  const gate = new Promise((resolveGate) => { release = resolveGate })
  const quota = structuredClone(baseQuota)
  if (scenario === 'low-available') Object.assign(quota, { available: '0.001', settled: '44.999' })
  if (scenario === 'cross-day-unknown') Object.assign(quota, {
    business_date: '2026-10-15', available: '48.000', reserved: '0.000', settled: '0.000', unknown: '0.000',
    historical_unknown: '1.234', historical_reserved: '0.766', pending_max: '10.000', pending_available: '8.000',
    breakdown: {
      text: { reserved: '0.000', settled: '0.005', unknown: '0.000' },
      image: { reserved: '0.000', settled: '0.000', unknown: '0.000' },
      video: { reserved: '0.000', settled: '0.000', unknown: '0.000' },
    },
  })
  if (scenario === 'unconfigured-prices') quota.diagnostics.pricing_configured = false
  if (scenario === 'legacy-reconciliation') quota.legacy_reconciliation_required = true
  await context.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== fixture.origin) {
      report.safety.externalRequests.push({ scenario, width, url: request.url() })
      return route.abort()
    }
    if (!['GET', 'HEAD'].includes(request.method())) {
      report.safety.writeRequests.push({ scenario, width, path: url.pathname, method: request.method() })
      return route.fulfill({ status: 405, json: { detail: 'Offline check blocks every write' } })
    }
    if (url.pathname === '/api/v1/ai-usage/quota') {
      requestCount += 1
      if (requestCount === 1) await gate
      if (scenario === 'unauthorized') return route.fulfill({
        status: 401, json: { detail: { code: 'AUTH_REQUIRED', message: '请重新登录后查看额度' } },
      })
      if ((scenario === 'failure-retry' && requestCount === 1) || failRefresh) return route.fulfill({
        status: 503, json: { detail: { code: 'QUOTA_UNAVAILABLE', message: '额度暂不可读，请重试' } },
      })
      return route.fulfill({ status: 200, json: quota })
    }
    if (url.pathname.startsWith('/api/') && !fixture.responses.has(url.pathname) && url.pathname !== '/api/v1/tasks') {
      report.safety.unmatchedRequests.push({ width, scenario, path: url.pathname })
      return route.fulfill({ status: 404, json: { detail: 'No offline fixture route' } })
    }
    return route.continue()
  })
  // All WebSocket destinations are blocked too; the fixture needs no HMR.
  await context.routeWebSocket('**/*', (socket) => socket.close())
  const screenshot = async (name) => {
    const path = resolve(reportDir, `${scenario}-${width}-${name}.png`)
    await page.screenshot({ path, fullPage: true })
    result.screenshots.push(path)
  }
  try {
    await page.goto(`${fixture.origin}/?view=settings`)
    await page.getByRole('heading', { name: '偏好设置', exact: true }).waitFor()
    const settingsRoute = ROUTES.find((route) => route.name === 'settings')
    for (let attempt = 0; attempt < 30; attempt += 1) {
      result.smoke = await page.evaluate(collectPageSnapshot, settingsRoute)
      if (isPageReady(settingsRoute, result.smoke)) break
      await page.waitForTimeout(100)
    }
    assert(isPageReady(settingsRoute, result.smoke), 'Existing settings smoke contract must pass')
    const section = page.getByRole('region', { name: 'AI 每日额度', exact: true })
    await section.getByText('正在读取 AI 每日额度…', { exact: true }).waitFor()
    assert.equal(await section.locator('[data-budget-value]').count(), 0, 'Loading must not imply $50 available')
    const loadingRefresh = section.getByRole('button', { name: '刷新 AI 每日额度' })
    assert(await loadingRefresh.isDisabled())
    assert.equal(await loadingRefresh.getAttribute('title'), '刷新 AI 每日额度')
    await screenshot('loading')
    release()
    if (scenario === 'failure-retry' || scenario === 'unauthorized') {
      await section.getByRole('alert').waitFor()
      assert.equal(await section.locator('[data-budget-value]').count(), 0)
      assert(!(await section.innerText()).includes('$50'))
      await screenshot('error')
      if (scenario === 'unauthorized') {
        assert((await section.getByRole('alert').innerText()).includes('请重新登录'))
        await checkLayout(page, section)
        assert.deepEqual(errors, [])
        result.passed = true
        return
      }
      const retry = section.getByRole('button', { name: '重试读取 AI 每日额度' })
      await retry.focus()
      await page.keyboard.press('Enter')
    }
    await section.locator('[data-budget-value="total"] dd').waitFor()
    assert.equal(await section.locator('[data-budget-value]').count(), 5)
    assert.equal(await section.locator('[data-budget-value="total"] dd').innerText(), '$50.00')
    for (const key of ['available', 'reserved', 'settled', 'unknown']) {
      const expected = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 3 }).format(Number(quota[key]))
      assert.equal(await section.locator(`[data-budget-value="${key}"] dd`).innerText(), expected)
    }
    assert(!(await section.innerText()).includes('50000'))
    assert(!(await section.innerText()).includes('risk_units'))
    if (!quota.breakdown) assert.equal(await section.getByText('暂无分类用额数据', { exact: true }).count(), 3)
    if (scenario === 'normal') {
      assert((await section.innerText()).includes('未终结占用上限 未提供'))
      assert((await section.innerText()).includes('尚未接入'))
    }
    if (scenario === 'low-available') await section.getByText(/可用额度不足/).waitFor()
    if (scenario === 'legacy-reconciliation') await section.getByText(/历史用额需核查/).waitFor()
    if (scenario === 'unconfigured-prices') await section.getByText(/部分价格未配置/).waitFor()
    if (scenario === 'cross-day-unknown') {
      assert((await section.innerText()).includes('2026-10-15'))
      assert((await section.innerText()).includes('历史待核实 (UNKNOWN)：$1.234'))
      assert((await section.innerText()).includes('历史处理中预占：$0.766'))
      assert((await section.innerText()).includes('不会因跨日自动释放'))
      assert((await section.getByLabel('分类用额').innerText()).includes('$0.005'))
      assert((await section.innerText()).includes('未终结可用 $8.00'))
    }
    await checkLayout(page, section)
    await screenshot('ready')
    if (width === 390) {
      for (const selector of ['.ai-budget-history', '.ai-budget-categories', '.ai-budget-scope']) {
        const target = section.locator(selector)
        await target.evaluate((node) => node.scrollIntoView({ block: 'center', behavior: 'instant' }))
        assert(await target.evaluate((node) => {
          const rect = node.getBoundingClientRect()
          const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
          return node === hit || node.contains(hit)
        }), 'Mobile budget details must be reachable without navigation occlusion')
      }
      await section.locator('.ai-budget-history').evaluate((node) => node.scrollIntoView({ block: 'center', behavior: 'instant' }))
      const path = resolve(reportDir, `${scenario}-${width}-details.png`)
      await page.screenshot({ path })
      result.screenshots.push(path)
      result.mobileDetailsReachable = true
    }
    if (scenario === 'failure-retry') {
      failRefresh = true
      await section.getByRole('button', { name: '刷新 AI 每日额度' }).click()
      await section.getByRole('alert').waitFor()
      assert.equal(await section.locator('[data-budget-value]').count(), 0, 'Failed refresh must hide stale balances')
      await screenshot('refresh-error')
      failRefresh = false
      await section.getByRole('button', { name: '重试读取 AI 每日额度' }).click()
      await section.locator('[data-budget-value="total"] dd').waitFor()
      assert.equal(await section.getByRole('alert').count(), 0)
    }
    assert.deepEqual(errors, [])
    result.passed = true
  } catch (error) {
    result.error = error.stack
    release()
    await screenshot('failed').catch(() => {})
    throw error
  } finally {
    release()
    await context.close()
  }
}

try {
  fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'vite-cache') })
  browser = await chromium.launch({ headless: true })
  report.browserVersion = browser.version()
  for (const [width, height] of [[1440, 900], [1024, 768], [768, 1024], [390, 844]]) {
    for (const scenario of scenarios) {
      await run(width, height, scenario)
      console.log(`PASS ${width} ${scenario}`)
    }
  }
  assert.deepEqual(report.safety.externalRequests, [])
  assert.deepEqual(report.safety.writeRequests, [])
  assert.deepEqual(report.safety.unmatchedRequests, [])
  assert.deepEqual(fixture.state.writes, [])
  assert.deepEqual(fixture.state.unexpected, [])
} finally {
  await browser?.close()
  await fixture?.server.close()
  await writeFile(resolve(reportDir, 'report.json'), JSON.stringify(report, null, 2))
}
console.log(`AI budget: ${report.cases.length} cases passed. Evidence: ${reportDir}`)
