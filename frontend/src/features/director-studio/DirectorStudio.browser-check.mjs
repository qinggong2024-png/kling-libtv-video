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
const browser = await chromium.launch(process.env.DIRECTOR_BROWSER_PATH
  ? { executablePath: process.env.DIRECTOR_BROWSER_PATH, headless: true }
  : { channel: 'msedge', headless: true })
const report = { browser: browser.version(), cases: [], externalRequests: [], sourceHashes: {} }
for (const file of ['DirectorStudio.tsx', 'DirectorPlanningViews.tsx', 'directorPresentation.ts', 'directorStudio.css', 'directorApi.ts', 'directorModel.ts', 'productionBridge.ts']) {
  report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, 'frontend/src/features/director-studio', file))).digest('hex')
}
try {
  for (const width of [1440, 1024, 768, 390]) {
    const context = await browser.newContext({ viewport: { width, height: ({ 390: 844, 768: 1024, 1024: 768 })[width] ?? 900 }, serviceWorkers: 'block' })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const commands = []
    let failReview = false
    let failSelect = false
    let uncertain = false
    const task = {
      id: 'task-1', status: 'DRAFT', state_version: 0, mode: 'OFFLINE_FAKE_ONLY',
      snapshot: {
        asset: {}, candidates: [], trace: [],
        storyboard: { packages: {}, candidates: [], selections: {}, latest_reviews: {} },
      },
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
      if (url.pathname === '/api/v1/site-style-profiles') return json([])
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
          task.snapshot.package = {
            package_id: 'package-1', revision: 3, parent_package_id: null,
            locks_hash: 'a'.repeat(64), preservation_hash: 'b'.repeat(64), facts_revision: 2,
            ruleset: 'offline-rules-v1', shot_id: 'FIRST_FRAME',
            prompt: 'Read-only server prompt\nPreserve the original garment.',
            reality: [{ dimension: 'fabric', decision: 'preserve', evidence: 'Observed original garment' }],
          }
        } else if (body.action === 'authorize') {
          if (task.snapshot.authorization) {
            assert.equal(body.authorization.parent_authorization_id, task.snapshot.authorization.authorization_id)
          }
          task.snapshot.authorization = body.authorization
          if (body.authorization.scope === 'VIDEO_STORYBOARD') {
            assert(task.snapshot.selection && task.snapshot.candidates[0].qualified)
            task.snapshot.storyboard.packages.SHOT_01 = {
              package_id: 'storyboard-package-1',
              revision: 4, parent_package_id: 'package-1', facts_revision: 2,
              locks_hash: 'c'.repeat(64), preservation_hash: 'd'.repeat(64), ruleset: 'offline-rules-v1',
              shot_id: 'SHOT_01',
              purpose: 'VIDEO_STORYBOARD',
              prompt: 'Read-only storyboard prompt', reality: [],
            }
            task.snapshot.authorization.package_id = 'storyboard-package-1'
          }
        } else if (body.action === 'generate') {
          if (body.shot_id === 'SHOT_01') {
            assert.equal(body.package_id, task.snapshot.authorization.package_id)
            task.status = 'STORYBOARD_REVIEW'
            task.snapshot.storyboard.candidates = [{ candidate_id: 'storyboard-candidate-1', package_id: 'storyboard-package-1', shot_id: 'SHOT_01', synthetic: true, qualified: false }]
          } else {
            task.status = 'IMAGE_REVIEW'
            task.snapshot.candidates = [{ candidate_id: 'candidate-1', package_id: 'package-1', shot_id: 'FIRST_FRAME', synthetic: true, qualified: false }]
          }
        } else if (body.action === 'review') {
          const isStoryboard = body.shot_id === 'SHOT_01'
          const candidates = isStoryboard ? task.snapshot.storyboard.candidates : task.snapshot.candidates
          candidates[0].qualified = body.decision === 'QUALIFIED'
          const review = {
              candidate_id: body.candidate_id,
              reviewer_id: 'reviewer-1',
              decision: body.decision,
              qualification_scope: 'OFFLINE_SYNTHETIC_ONLY',
              reason: body.reason ?? null,
          }
          if (isStoryboard) {
            task.snapshot.storyboard.latest_reviews.SHOT_01 = review
            delete task.snapshot.storyboard.selections.SHOT_01
          } else {
            task.snapshot.latest_review = review
            delete task.snapshot.selection
          }
        } else if (body.action === 'select') {
          if (body.shot_id === 'SHOT_01') {
            assert(task.snapshot.storyboard.candidates[0].qualified)
            task.snapshot.storyboard.selections.SHOT_01 = { candidate_id: body.candidate_id, package_id: 'storyboard-package-1', shot_id: 'SHOT_01', synthetic: true }
          } else {
            assert(task.snapshot.candidates[0].qualified)
            task.snapshot.selection = { candidate_id: body.candidate_id, package_id: 'package-1', shot_id: 'FIRST_FRAME', synthetic: true }
          }
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
      await page.getByText('完成 Product Brief 后生成创意方向', { exact: true }).waitFor()
      await page.screenshot({ path: resolve(evidence, `brief-${width}.png`), fullPage: true })
      await page.locator('input[type=file]').setInputFiles({
        name: 'front.png', mimeType: 'image/png',
        buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=', 'base64'),
      })
      await page.getByRole('button', { name: '生成创意方向', exact: true }).click()
      const directionCards = page.locator('button.director-direction')
      await directionCards.filter({ hasText: 'scene A' }).waitFor()
      assert.equal(await directionCards.count(), 3)
      assert.equal(await page.locator('.director-direction__label').filter({ hasText: 'Execution Concept' }).count(), 3)
      assert.equal(await page.locator('.director-direction__label').filter({ hasText: 'Visual Proposal' }).count(), 3)
      assert.equal(await page.locator('.director-direction__source-list strong').filter({ hasText: 'Creative Proposal' }).count(), 3)
      assert.equal(await page.getByText('Information Source', { exact: true }).count(), 3)
      assert.equal(await page.getByRole('region', { name: '方向差异对比' }).count(), 0)
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No direction card overflow')
      if (width === 390) {
        const firstCard = await directionCards.first().boundingBox()
        assert(firstCard && firstCard.y < 844, 'Direction card starts within the mobile viewport')
        assert(await directionCards.first().getByText('干净街拍', { exact: true }).isVisible())
        assert(await directionCards.first().getByText('选择', { exact: true }).isVisible())
      }
      await page.screenshot({ path: resolve(evidence, `directions-${width}.png`), fullPage: true })
      const directionA = page.locator('button.director-direction').filter({ hasText: '干净街拍' })
      const directionB = page.locator('button.director-direction').filter({ hasText: '安静质感' })
      await directionA.click()
      assert.equal(commands.filter(command => command.action === 'select_direction').length, 0, 'Selecting a direction does not confirm it')
      assert.equal(await page.getByRole('region', { name: 'FIRST_FRAME 生产包证据' }).count(), 0, 'Selecting a direction does not create a package')
      assert(await directionA.getByText('已选择', { exact: true }).isVisible())
      const confirmDirection = page.getByRole('button', { name: '确认方向：A · 干净街拍', exact: true })
      assert(await confirmDirection.isEnabled(), 'Confirm direction is the only executable direction action')
      await directionB.click()
      assert(await directionB.getByText('已选择', { exact: true }).isVisible())
      assert(await directionA.getByText('选择', { exact: true }).isVisible())
      assert.equal(commands.filter(command => command.action === 'select_direction').length, 0, 'Switching direction does not confirm it')
      await directionA.click()
      await page.getByRole('button', { name: '确认方向：A · 干净街拍', exact: true }).click()
      const firstFramePackage = page.getByRole('region', { name: 'FIRST_FRAME 生产包证据' })
      await firstFramePackage.getByText('r3', { exact: true }).waitFor()
      assert.equal(commands.filter(command => command.action === 'select_direction').length, 1, 'Confirming a direction creates one select_direction command')
      const spatial = page.getByRole('region', { name: '空间与关键视觉规划' })
      await spatial.getByText('Key Visual Shot Selector', { exact: true }).waitFor()
      assert.equal(await spatial.locator('.director-camera-row').count(), 3)
      assert.equal(await spatial.locator('.director-actor-row').count(), 4)
      assert.equal(await spatial.locator('.director-key-visual').count(), 4)
      assert.equal(await spatial.locator('.director-key-visuals__counts strong').nth(0).textContent(), '4')
      assert.equal(await spatial.locator('.director-key-visuals__counts strong').nth(1).textContent(), '4')
      assert.equal(await spatial.locator('.director-key-visuals__counts strong').nth(2).textContent(), '3')
      await spatial.getByRole('button', { name: '合并前一帧' }).last().click()
      assert.equal(await spatial.locator('.director-key-visuals__counts strong').nth(1).textContent(), '3')
      assert.equal(await spatial.locator('.director-key-visuals__counts strong').nth(2).textContent(), '3')
      assert.equal(await spatial.locator('.director-key-visuals__counts strong').nth(3).textContent(), '0')
      await firstFramePackage.getByText('Prompt · 服务端只读', { exact: true }).click()
      await firstFramePackage.getByText('Reality 决策 · 1 项', { exact: true }).click()
      assert(await firstFramePackage.getByText('Observed original garment', { exact: true }).isVisible())
      const bridge = page.getByRole('region', { name: 'Production Bridge Preparation' })
      await bridge.getByText('服务端预检要求 · 10 项', { exact: true }).click()
      assert.equal(await bridge.getByText('待服务端验证', { exact: true }).count(), 10)
      assert(await bridge.getByText('PREFLIGHT_REQUIRED', { exact: true }).isVisible())
      assert.equal(await bridge.getByRole('button').count(), 0, 'Bridge has no submission control')
      await page.screenshot({ path: resolve(evidence, `package-bridge-${width}.png`), fullPage: true })
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
      assert(await page.getByRole('status').filter({ hasText: 'STALE_VERSION' }).isVisible())
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
      await page.screenshot({ path: resolve(evidence, `first-frame-selected-${width}.png`), fullPage: true })
      await reject.click()
      await candidate.getByText('服务端审核：已拒绝', { exact: true }).waitFor()
      await candidate.getByText('服务端拒绝理由：印花与原商品不一致', { exact: true }).waitFor()
      assert(await select.isDisabled())
      assert(await candidate.getByText('首帧选择：未选择', { exact: true }).isVisible())
      assert.equal(commands.at(-1).reason, '印花与原商品不一致')
      assert.equal(await page.getByRole('button', { name: '授权 Fake 分镜', exact: true }).count(), 0)
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
      assert(await bridge.getByText(/执行证据为 UNKNOWN/).isVisible())
      uncertain = false
      await page.getByRole('button', { name: '刷新任务状态', exact: true }).click()
      await approve.click()
      await candidate.getByText('服务端审核：合格（仅离线范围）', { exact: true }).waitFor()
      await select.click()
      await candidate.getByText('首帧选择：已选择（仅离线）', { exact: true }).waitFor()
      await page.getByRole('button', { name: '授权 Fake 分镜', exact: true }).click()
      await page.getByRole('region', { name: 'SHOT_01 生产包证据' }).getByText('r4', { exact: true }).waitFor()
      await page.getByRole('button', { name: '生成 Fake 分镜', exact: true }).click()
      const storyboardCandidate = page.getByRole('region', { name: '分镜候选 1', exact: true })
      await storyboardCandidate.waitFor()
      const storyboardApprove = storyboardCandidate.getByRole('button', { name: '离线审核合格', exact: true })
      const storyboardSelect = storyboardCandidate.getByRole('button', { name: '选择离线分镜', exact: true })
      assert(await storyboardSelect.isDisabled())
      await storyboardApprove.click()
      await page.locator('.director-storyboard').getByText('服务端审核：合格（仅离线范围）', { exact: false }).waitFor()
      await storyboardSelect.click()
      await storyboardCandidate.getByText('分镜选择：已选择（仅离线）', { exact: true }).waitFor()
      await storyboardCandidate.getByRole('textbox').fill('分镜商品不一致')
      await storyboardCandidate.getByRole('button', { name: '拒绝候选', exact: true }).click()
      await storyboardCandidate.getByText('服务端拒绝理由：分镜商品不一致', { exact: true }).waitFor()
      assert(await storyboardSelect.isDisabled())
      assert(await candidate.getByText('首帧选择：已选择（仅离线）', { exact: true }).isVisible())
      await page.getByRole('button', { name: '刷新任务状态', exact: true }).click()
      await storyboardCandidate.getByText('服务端拒绝理由：分镜商品不一致', { exact: true }).waitFor()
      await storyboardApprove.click()
      await page.locator('.director-storyboard').getByText('服务端审核：合格（仅离线范围）', { exact: false }).waitFor()
      await storyboardSelect.click()
      await storyboardCandidate.getByText('分镜选择：已选择（仅离线）', { exact: true }).waitFor()
      uncertain = true
      await page.getByRole('button', { name: '刷新任务状态', exact: true }).click()
      await page.getByRole('status').filter({ hasText: '已读取服务端状态' }).waitFor()
      assert(await storyboardApprove.isDisabled())
      assert(await storyboardCandidate.getByRole('button', { name: '已选择离线分镜', exact: true }).isDisabled())
      assert.equal(commands.find(command => command.action === 'authorize' && command.authorization?.scope === 'VIDEO_STORYBOARD').authorization.shot_ids[0], 'SHOT_01')
      assert.equal(commands.find(command => command.action === 'generate' && command.shot_id === 'SHOT_01').shot_id, 'SHOT_01')
      assert.equal(commands.find(command => command.action === 'select' && command.shot_id === 'SHOT_01').shot_id, 'SHOT_01')
      await page.screenshot({ path: resolve(evidence, `selected-${width}.png`), fullPage: true })
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No page overflow')
      assert(await page.locator('.director-upload img').evaluate(img => img.complete && img.naturalWidth > 0), 'Product preview renders')
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
