import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const root = resolve(process.argv[2] || '.')
const evidence = resolve(process.env.HUMAN_REVIEW_EVIDENCE_DIR || '../human-review-evidence')
assert(process.env.PLAYWRIGHT_MODULE, 'PLAYWRIGHT_MODULE is required')
assert(process.env.HUMAN_REVIEW_PYTHON, 'HUMAN_REVIEW_PYTHON is required')
await mkdir(evidence, { recursive: true })
const databaseDirectory = await mkdtemp(resolve(evidence, 'database-'))
const requireFrontend = createRequire(resolve(root, 'frontend/package.json'))
const { createServer } = await import(pathToFileURL(requireFrontend.resolve('vite')).href)
const { chromium } = requireFrontend(process.env.PLAYWRIGHT_MODULE)

// Reuse the tested database fixture with the real router; no provider is mounted.
const child = spawn(process.env.HUMAN_REVIEW_PYTHON, ['-u', '-c', `
import asyncio, importlib.util, json, socket
from pathlib import Path
import uvicorn
spec = importlib.util.spec_from_file_location("review_fixture", "backend/tests/test_human_production_reviews.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
async def main():
    fixture = module.review_env.__wrapped__(Path(${JSON.stringify(databaseDirectory)}))
    env = await anext(fixture)
    env.app.state.settings.ai_adapter_mode = "fake"
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    server = uvicorn.Server(uvicorn.Config(env.app, log_level="error"))
    print("READY " + json.dumps({"origin": "http://127.0.0.1:" + str(sock.getsockname()[1]),
          "owner": str(env.ids["owner"]), "image": env.image, "video": env.video,
          "director": env.director}), flush=True)
    try:
        await server.serve(sockets=[sock])
    finally:
        await fixture.aclose()
asyncio.run(main())
`], { cwd: root, env: { ...process.env, PYTHONPATH: resolve(root, 'backend/src') }, stdio: ['ignore', 'pipe', 'pipe'] })
let stderr = ''
child.stderr.on('data', data => { stderr += data.toString() })
const fixture = await new Promise((resolveReady, reject) => {
  let output = ''
  const timer = setTimeout(() => reject(new Error(`Backend startup timed out: ${stderr}`)), 30000)
  child.once('exit', code => { clearTimeout(timer); reject(new Error(`Backend exited ${code}: ${stderr}`)) })
  child.stdout.on('data', data => {
    output += data.toString()
    const ready = output.split('\n').find(line => line.startsWith('READY '))
    if (ready) { clearTimeout(timer); resolveReady(JSON.parse(ready.slice(6))) }
  })
}).catch(error => { child.kill(); throw error })
const html = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Human Review Acceptance</title></head>
<body><main id="root" style="max-width:900px;margin:24px auto;padding:0 16px;min-width:0"></main>
<script type="module">
import React from 'react'
import { createRoot } from 'react-dom/client'
import { HumanReviewPanel } from '/src/features/human-review/HumanReviewPanel.tsx'
import { setApiUserId } from '/src/api.ts'
import '/src/styles.css'
setApiUserId(${JSON.stringify(fixture.owner)})
const subjects = ${JSON.stringify([fixture.image, fixture.video, fixture.director])}
const readOnly = new URLSearchParams(location.search).has('readonly')
createRoot(document.getElementById('root')).render(React.createElement('div', {},
  ...subjects.map(subject => React.createElement('section', { key: subject.subjectType, 'aria-label': subject.subjectType },
    React.createElement('h2', {}, subject.subjectType),
    React.createElement(HumanReviewPanel, { subjectType: subject.subjectType, subjectId: subject.subjectId,
      taskId: subject.taskId, canWrite: !readOnly })))))
</script></body></html>`
let server
let browser
const report = { mode: 'OFFLINE_SYNTHETIC_ONLY', realReviewAPI: true, viewports: [], scenarios: [], forbiddenRequests: [], pageErrors: [] }
try {
  server = await createServer({
    configFile: false, envFile: false, root: resolve(root, 'frontend'),
    cacheDir: resolve(evidence, 'vite-cache'), logLevel: 'error',
    server: { host: '127.0.0.1', port: 0, proxy: { '/api': fixture.origin } },
    plugins: [{
      name: 'human-review-isolated-acceptance',
      configureServer(vite) {
        vite.middlewares.use(async (req, res, next) => {
          if (new URL(req.url, 'http://127.0.0.1').pathname !== '/') return next()
          res.setHeader('Content-Type', 'text/html; charset=utf-8')
          res.end(await vite.transformIndexHtml('/', html))
        })
      },
    }],
  })
  await server.listen()
  const origin = server.resolvedUrls.local[0]
  browser = await chromium.launch({ headless: true })
  async function open(width = 1440, suffix = '') {
    const context = await browser.newContext({ viewport: { width, height: 1050 }, serviceWorkers: 'block' })
    const page = await context.newPage()
    page.on('pageerror', error => report.pageErrors.push(String(error)))
    await context.route('**/*', route => {
      const request = route.request()
      const url = new URL(request.url())
      if (!request.url().startsWith(origin) || (url.pathname.startsWith('/api') && !url.pathname.startsWith('/api/v1/human-reviews'))) {
        report.forbiddenRequests.push(request.url())
        return route.abort()
      }
      return route.continue()
    })
    await page.goto(`${origin}${suffix}`)
    return { context, page }
  }
  const subjectQuery = body => new URLSearchParams(Object.fromEntries(['subjectType', 'subjectId', 'taskId'].filter(key => body[key]).map(key => [key, body[key]]))).toString()
  const apiHistory = async (page, body) => (await page.request.get(`${origin}api/v1/human-reviews?${subjectQuery(body)}`, { headers: { 'X-User-Id': fixture.owner } })).json()
  const panel = (page, type) => page.getByRole('region', { name: type, exact: true })
  async function expand(region) {
    await region.locator('summary').click()
    await region.getByRole('radio', { name: 'PASS', exact: true }).waitFor()
  }
  for (const width of [1440, 1024, 768, 390]) {
    const { context, page } = await open(width)
    const image = panel(page, 'IMAGE_OUTPUT')
    await expand(image)
    await image.getByRole('radio', { name: 'REWORK', exact: true }).check()
    assert(await image.getByRole('button', { name: '保存人工评价', exact: true }).isDisabled())
    await image.getByRole('checkbox', { name: 'OTHER', exact: false }).check()
    assert(await image.getByRole('button', { name: '保存人工评价', exact: true }).isDisabled())
    await image.getByRole('textbox').fill(`Garment detail needs correction ${width}`)
    await image.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await image.getByRole('status').filter({ hasText: '已记录人工评价' }).waitFor()
    await image.getByRole('radio', { name: 'FAIL', exact: true }).check()
    await image.getByRole('checkbox', { name: 'GARMENT', exact: false }).check()
    await image.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await image.getByRole('status').filter({ hasText: '已记录人工评价' }).waitFor()
    await image.getByRole('radio', { name: 'PASS', exact: true }).check()
    await image.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await image.getByRole('status').filter({ hasText: '已记录人工评价' }).waitFor()
    const history = await apiHistory(page, fixture.image)
    assert.deepEqual(history.reviews.slice(-3).map(review => review.verdict), ['REWORK', 'FAIL', 'PASS'])
    assert.deepEqual(history.reviews.at(-1).reasonCodes, [])
    const video = panel(page, 'VIDEO_VARIANT')
    await expand(video)
    assert.equal(await video.getByRole('radio', { name: 'REWORK', exact: true }).count(), 0)
    await video.getByRole('radio', { name: 'FAIL', exact: true }).check()
    await video.getByRole('checkbox', { name: 'MOTION', exact: false }).check()
    await video.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await video.getByRole('status').filter({ hasText: '已记录人工评价' }).waitFor()
    await video.getByRole('radio', { name: 'PASS', exact: true }).check()
    await video.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await video.getByRole('status').filter({ hasText: '已记录人工评价' }).waitFor()
    const director = panel(page, 'DIRECTOR_CANDIDATE')
    await expand(director)
    await director.getByRole('radio', { name: 'REWORK', exact: true }).check()
    await director.getByRole('checkbox', { name: 'SPACE', exact: false }).check()
    await director.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await director.getByRole('status').filter({ hasText: '已记录人工评价' }).waitFor()
    const downloadEvent = page.waitForEvent('download')
    await image.getByRole('button', { name: '下载评价数据', exact: true }).click()
    const download = await downloadEvent
    const path = resolve(evidence, `export-${width}.json`)
    await download.saveAs(path)
    const exported = JSON.parse(await readFile(path, 'utf8'))
    assert.equal(exported.schemaVersion, 'human-production-review-export.v1')
    assert.deepEqual(exported.records, [])
    assert.equal(exported.excludedSyntheticCount, history.reviews.length)
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.screenshot({ path: resolve(evidence, `review-${width}.png`), fullPage: true })
    await page.reload()
    await expand(panel(page, 'IMAGE_OUTPUT'))
    assert.equal(await panel(page, 'IMAGE_OUTPUT').locator('.human-review__history li').count(), history.reviews.length)
    report.viewports.push({ width, imageThreeStates: true, videoTwoStates: true, storyboardReview: true, historyReload: true, syntheticExcluded: true, layout: true })
    await context.close()
  }
  {
    const { page, context } = await open()
    const image = panel(page, 'IMAGE_OUTPUT')
    await expand(image)
    const before = await apiHistory(page, fixture.image)
    let savedInput
    await page.route('**/api/v1/human-reviews', async route => {
      if (route.request().method() !== 'POST') return route.fallback()
      savedInput = route.request().postDataJSON()
      const response = await route.fetch()
      assert.equal(response.status(), 201)
      await route.abort('failed')
    }, { times: 1 })
    await image.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await image.getByRole('status').filter({ hasText: '保存结果待确认' }).waitFor()
    assert(await image.getByRole('radio', { name: 'PASS', exact: true }).isDisabled())
    await page.reload()
    await expand(panel(page, 'IMAGE_OUTPUT'))
    await panel(page, 'IMAGE_OUTPUT').getByRole('status').filter({ hasText: '已确认上次评价已记录' }).waitFor()
    const after = await apiHistory(page, fixture.image)
    assert.equal(after.reviews.length, before.reviews.length + 1)
    assert.equal(after.reviews.filter(review => review.reviewKey === savedInput.reviewKey).length, 1)
    report.scenarios.push('committed-response-loss-reload-reconciles-once')
    await context.close()
  }
  {
    const { page, context } = await open(390)
    const video = panel(page, 'VIDEO_VARIANT')
    await expand(video)
    const before = await apiHistory(page, fixture.video)
    let original
    await page.route('**/api/v1/human-reviews', async route => {
      original = route.request().postDataJSON()
      await route.abort('failed')
    }, { times: 1 })
    await video.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await video.getByRole('status').filter({ hasText: '保存结果待确认' }).waitFor()
    await page.reload()
    await expand(panel(page, 'VIDEO_VARIANT'))
    let retry
    await page.route('**/api/v1/human-reviews', async route => {
      retry = route.request().postDataJSON()
      await route.continue()
    }, { times: 1 })
    await panel(page, 'VIDEO_VARIANT').getByRole('button', { name: '重试同一评价', exact: true }).click()
    await panel(page, 'VIDEO_VARIANT').getByRole('status').filter({ hasText: '已记录人工评价' }).waitFor()
    assert.deepEqual(retry, original)
    assert.equal((await apiHistory(page, fixture.video)).reviews.length, before.reviews.length + 1)
    report.scenarios.push('unsubmitted-network-loss-retries-identical-key-payload-after-reload')
    await context.close()
  }
  {
    const { page, context } = await open(390, '?readonly=1')
    const image = panel(page, 'IMAGE_OUTPUT')
    await expand(image)
    assert(await image.getByRole('radio', { name: 'PASS', exact: true }).isDisabled())
    assert(await image.getByRole('button', { name: '保存人工评价', exact: true }).isDisabled())
    assert(!(await image.getByRole('button', { name: '下载评价数据', exact: true }).isDisabled()))
    report.scenarios.push('readonly-history-and-export-without-write')
    await context.close()
  }
  {
    const { page, context } = await open()
    const image = panel(page, 'IMAGE_OUTPUT')
    await expand(image)
    await page.route('**/api/v1/human-reviews', route => route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'HUMAN_REVIEW_OUTPUT_HASH_MISMATCH', message: 'Result changed' } }) }), { times: 1 })
    await image.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await image.getByRole('status').filter({ hasText: 'Result changed' }).waitFor()
    assert(!(await image.getByRole('radio', { name: 'PASS', exact: true }).isDisabled()))
    assert.equal(await image.getByRole('button', { name: '重试同一评价', exact: true }).count(), 0)
    await page.evaluate(() => { Storage.prototype.setItem = () => { throw new Error('Storage blocked') } })
    await image.getByRole('button', { name: '保存人工评价', exact: true }).click()
    await image.getByRole('status').filter({ hasText: '恢复信息无法保存，评价未提交' }).waitFor()
    report.scenarios.push('definitive-rejection-unlocks-form-and-storage-failure-blocks-submit')
    await context.close()
  }
  assert.deepEqual(report.forbiddenRequests, [])
  assert.deepEqual(report.pageErrors, [])
  report.passed = true
  console.log(JSON.stringify(report))
} finally {
  await writeFile(resolve(evidence, 'report.json'), JSON.stringify(report, null, 2))
  await browser?.close()
  await server?.close()
  const stopped = new Promise(resolveExit => child.once('exit', resolveExit))
  child.kill()
  await stopped
}
