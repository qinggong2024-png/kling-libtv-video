import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const root = resolve(process.argv[2] || '.')
const evidence = resolve(process.env.DIRECTOR_EVIDENCE_DIR)
assert(process.env.PLAYWRIGHT_MODULE && process.env.DIRECTOR_EVIDENCE_DIR)
const require = createRequire(resolve(root, 'frontend/package.json'))
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE)
await mkdir(evidence, { recursive: true })
const server = await createServer({
  configFile: false, envFile: false, root: resolve(root, 'frontend'),
  cacheDir: resolve(evidence, 'vite-cache'), logLevel: 'error',
  server: { host: '127.0.0.1', port: 0 },
  plugins: [{
    name: 'isolated-director-fixture',
    configureServer(vite) {
      vite.middlewares.use(async (req, res, next) => {
        if (req.url !== '/') return next()
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        res.end(await vite.transformIndexHtml('/', `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
          import React from 'react'; import {createRoot} from 'react-dom/client';
          import {DirectorStudio} from '/src/features/director-studio/DirectorStudio.tsx';
          import '/src/styles.css';
          createRoot(document.getElementById('root')).render(React.createElement(DirectorStudio));
        </script></body></html>`))
      })
    },
  }],
})
await server.listen()
const origin = `http://127.0.0.1:${server.httpServer.address().port}`
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const report = { browser: browser.version(), cases: [], externalRequests: [], sourceHashes: {} }
for (const file of ['DirectorStudio.tsx', 'directorApi.ts', 'directorModel.ts']) {
  report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, 'frontend/src/features/director-studio', file))).digest('hex')
}
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, serviceWorkers: 'block' })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const commands = []
    let failReview = false
    let failSelect = false
    let uncertain = false
    const task = {
      id: 'task-1', status: 'DRAFT', state_version: 0, mode: 'OFFLINE_FAKE_ONLY',
      snapshot: { asset: {}, candidates: [], trace: [] },
    }
    await context.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.origin !== origin && !['blob:', 'data:'].includes(url.protocol)) {
        report.externalRequests.push(url.origin)
        return route.abort()
      }
      if (!url.pathname.startsWith('/api/')) return route.continue()
      const json = value => route.fulfill({ json: value })
      if (url.pathname === '/api/v1/system/status') return json({ sharedAuthentication: false, csrfCookieName: 'csrf' })
      if (url.pathname === '/api/v1/auth/me') return json({ userId: 'user-1', username: 'fixture', role: 'USER' })
      if (url.pathname === '/api/v1/products') return json({ id: 'product-1' })
      if (url.pathname.endsWith('/commands')) {
        const body = route.request().postDataJSON()
        commands.push(body)
        assert.equal(body.expected_version, task.state_version)
        if ((body.action === 'review' && failReview) || (body.action === 'select' && failSelect)) {
          failReview = false
          failSelect = false
          return route.fulfill({ status: 409, json: { detail: { code: 'STALE_VERSION', message: '测试冲突，请刷新状态' } } })
        }
        await new Promise(done => setTimeout(done, 150))
        if (body.action === 'analyze') {
          task.status = 'AWAITING_DIRECTION'
          task.snapshot.plan = { directions: ['A', 'B', 'C'].map(id => ({ id, scene: `scene ${id}`, behavior: 'standing' })) }
        } else if (body.action === 'select_direction') {
          task.status = 'PLAN_READY'
          task.snapshot.plan.selected_direction = body.direction_id
          task.snapshot.package = { package_id: 'package-1', locks_hash: 'locks' }
        } else if (body.action === 'authorize') {
          task.snapshot.authorization = body.authorization
        } else if (body.action === 'generate') {
          task.status = 'IMAGE_REVIEW'
          task.snapshot.candidates = [{ candidate_id: 'candidate-1', package_id: 'package-1', shot_id: 'FIRST_FRAME', synthetic: true, qualified: false }]
        } else if (body.action === 'review') {
          task.snapshot.candidates[0].qualified = body.decision === 'QUALIFIED'
          task.snapshot.latest_review = {
            candidate_id: body.candidate_id,
            reviewer_id: 'reviewer-1',
            decision: body.decision,
            qualification_scope: 'OFFLINE_SYNTHETIC_ONLY',
            reason: body.reason ?? null,
          }
          delete task.snapshot.selection
        } else if (body.action === 'select') {
          assert(task.snapshot.candidates[0].qualified)
          task.snapshot.selection = { candidate_id: body.candidate_id, package_id: 'package-1', shot_id: 'FIRST_FRAME', synthetic: true }
        } else assert.fail(`Unexpected command ${body.action}`)
        task.state_version++
        return json(task)
      }
      if (url.pathname === '/api/v1/creative-workflow/tasks') return json(task)
      if (url.pathname.endsWith('/task-1')) {
        task.snapshot.execution_state = uncertain ? 'UNKNOWN' : 'SUCCEEDED'
        return json(task)
      }
      assert.fail(`Unexpected API ${url.pathname}`)
    })
    try {
      await page.goto(origin)
      await page.locator('input[type=file]').setInputFiles({
        name: 'front.png', mimeType: 'image/png',
        buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=', 'base64'),
      })
      await page.getByRole('button', { name: '创建任务并分析', exact: true }).click()
      await page.getByRole('button', { name: /A 干净街拍/ }).click()
      await page.getByRole('button', { name: '授权 Fake 首帧', exact: true }).click()
      await page.getByRole('button', { name: '生成 Fake 首帧', exact: true }).click()
      const candidate = page.getByRole('region', { name: '首帧候选 1', exact: true })
      await candidate.waitFor()
      const approve = candidate.getByRole('button', { name: '离线审核合格', exact: true })
      const reject = candidate.getByRole('button', { name: '拒绝候选', exact: true })
      const select = candidate.getByRole('button', { name: '选择离线首帧', exact: true })
      const reason = candidate.getByRole('textbox')
      assert(await select.isDisabled())
      assert(await reject.isDisabled())
      await reason.fill('   ')
      assert(await reject.isDisabled())
      await reason.fill('印花与原商品不一致')
      failReview = true
      await approve.click()
      await page.getByRole('status').filter({ hasText: '测试冲突' }).waitFor()
      assert(await select.isDisabled(), 'Failed review never enables selection')
      await page.getByRole('button', { name: '刷新任务状态', exact: true }).click()
      await approve.click()
      assert(await approve.isDisabled())
      assert(await reject.isDisabled())
      assert(await select.isDisabled())
      await approve.evaluate(button => button.click())
      await candidate.getByText('服务端审核：合格（仅离线范围）', { exact: true }).waitFor()
      assert.equal(commands.filter(command => command.action === 'review').length, 2, 'Busy repeat click creates no additional command')
      failSelect = true
      await select.click()
      await page.getByRole('status').filter({ hasText: '测试冲突' }).waitFor()
      assert(await candidate.getByText('首帧选择：未选择', { exact: true }).isVisible())
      await select.focus()
      await page.keyboard.press('Enter')
      await candidate.getByText('首帧选择：已选择（仅离线）', { exact: true }).waitFor()
      const selectionCommands = commands.filter(command => command.action === 'select')
      assert.equal(selectionCommands.length, 2)
      assert.equal(selectionCommands[0].command_key, selectionCommands[1].command_key, 'Retry preserves idempotency key')
      await page.screenshot({ path: resolve(evidence, `selected-${width}.png`), fullPage: true })
      await reject.click()
      await candidate.getByText('服务端审核：已拒绝', { exact: true }).waitFor()
      await candidate.getByText('服务端拒绝理由：印花与原商品不一致', { exact: true }).waitFor()
      assert(await select.isDisabled())
      assert(await candidate.getByText('首帧选择：未选择', { exact: true }).isVisible())
      assert.equal(commands.at(-1).reason, '印花与原商品不一致')
      await page.screenshot({ path: resolve(evidence, `rejected-${width}.png`), fullPage: true })
      await page.getByRole('button', { name: '刷新任务状态', exact: true }).click()
      await candidate.getByText('服务端审核：已拒绝', { exact: true }).waitFor()
      await candidate.getByText('服务端拒绝理由：印花与原商品不一致', { exact: true }).waitFor()
      uncertain = true
      await page.getByRole('button', { name: '刷新任务状态', exact: true }).click()
      await page.getByRole('status').filter({ hasText: '已读取服务端状态' }).waitFor()
      assert(await approve.isDisabled())
      assert(await reject.isDisabled())
      assert(await select.isDisabled())
      assert(await candidate.getByText(/OFFLINE_SYNTHETIC_ONLY/).isVisible())
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No page overflow')
      assert.deepEqual(errors, [])
      report.cases.push({ width, passed: true, commands: commands.length })
    } finally {
      if (errors.length) console.error(errors)
      await page.screenshot({ path: resolve(evidence, `final-${width}.png`), fullPage: true })
      await context.close()
    }
  }
  assert.deepEqual(report.externalRequests, [])
} finally {
  await writeFile(resolve(evidence, 'report.json'), JSON.stringify(report, null, 2))
  await browser.close()
  await server.close()
}
console.log(JSON.stringify(report.cases))
