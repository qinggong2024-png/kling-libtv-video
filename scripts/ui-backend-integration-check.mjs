import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { ROUTES, collectPageSnapshot, isPageReady } from './ui-smoke.mjs'

const origin = new URL(process.env.INTEGRATION_BASE_URL || 'http://127.0.0.1:5186').origin
assert.equal(new URL(origin).hostname, '127.0.0.1')
assert(!['5173', '8000', '8012'].includes(new URL(origin).port), 'Use the isolated Safe stack')
assert(process.env.PLAYWRIGHT_MODULE && process.env.INTEGRATION_EVIDENCE_DIR)
const evidence = resolve(process.env.INTEGRATION_EVIDENCE_DIR)
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE)
await mkdir(evidence, { recursive: true })
const browser = await chromium.launch({
  executablePath: process.env.INTEGRATION_BROWSER_PATH,
  headless: true,
})
const report = { origin, pages: [], responses: [], blockedRequests: [], errors: [] }
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' })
  const read = async (path, admin = false) => {
    const response = await context.request.get(`${origin}/api/v1${path}`, {
      headers: { 'X-User-Id': admin ? '00000000-0000-0000-0000-000000000099' : '00000000-0000-0000-0000-000000000001' },
    })
    assert.equal(response.status(), 200, path)
    return response.json()
  }
  const status = await read('/system/status')
  assert.equal(status.environment, 'test')
  assert.equal(status.sharedAuthentication, false)
  assert.equal(status.paidGenerationEnabled, false)
  assert.equal(status.paidGenerationAuthorized, false)
  assert.equal(status.openaiConfigured, false)
  assert.equal(status.directorWorkflowMode, 'offline_demo')
  assert.equal(status.videoGeneration.available, false)
  report.runtime = status
  report.readiness = await read('/health/ready')
  for (const path of ['/tasks', '/image-generation-batches', '/creative-workflow/tasks']) {
    assert.deepEqual(await read(path), [], 'Fresh integration database only')
  }
  const operations = await read('/admin/operations', true)
  assert(operations.runners.some(runner => runner.status === 'ONLINE' && runner.lastHeartbeatAt))
  report.workerOnline = true
  // No API mocks: only prevent writes and outbound requests during this read-only check.
  await context.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if ((url.origin !== origin && !['blob:', 'data:'].includes(url.protocol))
      || (url.pathname.startsWith('/api/') && request.method() !== 'GET')) {
      report.blockedRequests.push({ url: request.url(), method: request.method() })
      return route.abort()
    }
    return route.continue()
  })
  const page = await context.newPage()
  page.on('pageerror', error => report.errors.push(error.message))
  page.on('response', response => {
    if (new URL(response.url()).pathname.startsWith('/api/')) {
      report.responses.push({ path: new URL(response.url()).pathname, status: response.status() })
    }
  })
  const routes = ROUTES.filter(route => ['images', 'make', 'records', 'library', 'settings', 'admin-providers'].includes(route.name))
  routes.push({ name: 'director', query: '?view=images&pane=director', selector: '.director-studio', heading: '导演台' })
  for (const route of routes) {
    const historyReads = ['records', 'library'].includes(route.name)
      ? ['/tasks', '/image-generation-batches', '/creative-workflow/tasks'].map(path =>
        page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1${path}` && response.status() === 200))
      : []
    await page.goto(`${origin}/${route.query}`)
    await page.evaluate(admin => localStorage.setItem('development-actor-role', admin ? 'admin' : 'user'), Boolean(route.requiresAdmin))
    await page.reload()
    await page.waitForFunction(({ route, collect, ready }) => {
      const snapshot = new Function(`return (${collect})`)()(route)
      return new Function(`return (${ready})`)()(route, snapshot)
    }, { route, collect: collectPageSnapshot.toString(), ready: isPageReady.toString() }, { timeout: 20_000 })
    await Promise.all(historyReads)
    await page.screenshot({ path: resolve(evidence, `${route.name}.png`), fullPage: true })
    report.pages.push({ name: route.name, snapshot: await page.evaluate(collectPageSnapshot, route) })
  }
  for (const path of ['/tasks', '/image-generation-batches', '/creative-workflow/tasks']) {
    assert(report.responses.some(response => response.path === `/api/v1${path}` && response.status === 200), path)
  }
  assert.deepEqual(report.errors, [])
  assert.deepEqual(report.blockedRequests, [])
  assert(report.responses.every(response => response.status < 400
    || (response.path === '/api/v1/admin/kling/elements' && response.status === 409)),
  'Only the disabled Provider element capability may reject reads')
  report.passed = true
} finally {
  await browser.close()
  await writeFile(resolve(evidence, 'report.json'), JSON.stringify(report, null, 2))
}
console.log(JSON.stringify({ passed: report.passed, pages: report.pages.map(page => page.name), apiReads: report.responses.length }))
