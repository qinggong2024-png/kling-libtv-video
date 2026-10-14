import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const root = resolve(process.argv[2] || '.')
const evidence = resolve(process.env.DIRECTOR_DELIVERY_EVIDENCE_DIR || resolve(root, '..', 'director-delivery-evidence'))
const playwrightModule = process.env.PLAYWRIGHT_MODULE
assert(playwrightModule, 'PLAYWRIGHT_MODULE is required')

const frontendRequire = createRequire(resolve(root, 'frontend/package.json'))
const { createServer } = await import(pathToFileURL(frontendRequire.resolve('vite')).href)
const { chromium } = createRequire(resolve(root, 'frontend/package.json'))(playwrightModule)

await mkdir(evidence, { recursive: true })

const sourceFiles = [
  'frontend/src/creative-project/provider.tsx',
  'frontend/src/creative-project/recovery.ts',
  'frontend/src/features/director-studio/DirectorStudio.tsx',
  'frontend/src/features/director-studio/directorApi.ts',
  'frontend/src/features/director-studio/directorRecovery.ts',
  'frontend/src/features/director-studio/productionBridge.ts',
  'frontend/src/features/task-center/HomeView.tsx',
  'frontend/src/features/production/ProductionComposer.tsx',
]

function clone(value) {
  return structuredClone(value)
}

function makeTask() {
  return {
    id: 'director-task-1',
    status: 'DRAFT',
    state_version: 0,
    mode: 'OFFLINE_FAKE_ONLY',
    snapshot: {
      asset: {
        sha256: 'source-image-hash-1',
        width: 1,
        height: 1,
        object_key: 'offline/product/front.png',
      },
      product_version: {
        product_id: 'director-product-1',
        product_version_id: 'director-product-version-1',
        facts_revision: 2,
      },
      trace: [],
      candidates: [],
      calls: 0,
      cost_micros: 0,
      total_calls: 0,
      total_cost_micros: 0,
      storyboard: {
        packages: {},
        candidates: [],
        selections: {},
        latest_reviews: {},
        shot_mappings: {},
      },
    },
  }
}

function candidate({ id, packageId, shotId, authorizationId }) {
  return {
    candidate_id: id,
    package_id: packageId,
    authorization_id: authorizationId,
    shot_id: shotId,
    batch_id: `${id}-batch`,
    item_id: `${id}-item`,
    output_id: `${id}-output`,
    synthetic: true,
    qualified: false,
    revision_index: 1,
    sha256: 'candidate-output-hash-1',
    object_key: `offline/${id}.png`,
    media_evidence: 'synthetic fixture media',
  }
}

function packageRecord({ id, revision, parentId, shotId, purpose }) {
  return {
    package_id: id,
    revision,
    parent_package_id: parentId,
    locks_hash: `${id}-locks`,
    facts_revision: 2,
    preservation_hash: `${id}-preservation`,
    ruleset: 'offline-director-delivery-fixture-v1',
    purpose,
    shot_id: shotId,
    prompt: `Offline read-only ${shotId} prompt`,
    reality: [{ dimension: 'garment', decision: 'preserve', evidence: 'Synthetic fixture evidence' }],
  }
}

function makePageHtml() {
  return `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Creative Workflow Director Delivery Fixture</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module">
      import React, { useState } from 'react'
      import { createRoot } from 'react-dom/client'
      import { createCreativeProject } from '/src/creative-project/project.ts'
      import { CreativeProjectProvider } from '/src/creative-project/provider.tsx'
      import { DirectorStudio } from '/src/features/director-studio/DirectorStudio.tsx'
      import { HomeView } from '/src/features/task-center/HomeView.tsx'
      import '/src/styles.css'

      const initialProject = createCreativeProject({
        id: 'director-delivery-project',
        name: 'Director delivery fixture',
      })

      function FixtureApp() {
        const [view, setView] = useState(new URLSearchParams(location.search).get('view') === 'make' ? 'make' : 'director')
        const go = (next) => {
          const url = next === 'make' ? '?view=make' : '?view=director'
          history.pushState({}, '', url)
          setView(next)
        }
        return React.createElement(React.Fragment, null,
          React.createElement('nav', { 'aria-label': '测试导航' },
            React.createElement('button', { type: 'button', onClick: () => go('director') }, '导演工作流'),
            React.createElement('button', { type: 'button', onClick: () => go('make') }, '视频工作室'),
          ),
          view === 'director'
            ? React.createElement(DirectorStudio)
            : React.createElement(HomeView, {
                active: true,
                tasks: [],
                seed: null,
                system: null,
                actorId: null,
                onCreated: () => {},
                onOpen: () => {},
                onView: () => {},
                onPlay: () => {},
                onRemix: () => {},
                onFeedbackChanged: () => {},
              }),
        )
      }

      createRoot(document.getElementById('root')).render(
        React.createElement(CreativeProjectProvider, { initialProject },
          React.createElement(FixtureApp),
        ),
      )
    </script>
  </body>
</html>`
}

async function createFixtureServer(cacheDir) {
  const server = await createServer({
    configFile: false,
    envFile: false,
    root: resolve(root, 'frontend'),
    cacheDir,
    logLevel: 'error',
    server: { host: '127.0.0.1', port: 0, strictPort: false },
    plugins: [{
      name: 'director-delivery-fixture',
      configureServer(vite) {
        vite.middlewares.use(async (req, res, next) => {
          const url = new URL(req.url, 'http://127.0.0.1')
          if (url.pathname === '/' || url.pathname === '/?view=make' || url.pathname === '/?view=director') {
            res.setHeader('Content-Type', 'text/html; charset=utf-8')
            res.setHeader('Set-Cookie', 'director_fixture_csrf=fixture-csrf; Path=/; SameSite=Strict')
            return res.end(await vite.transformIndexHtml('/', makePageHtml()))
          }
          return next()
        })
      },
    }],
  })
  await server.listen()
  return { server, origin: server.resolvedUrls.local[0].replace(/\/$/, '') }
}

function baseCatalogResponses() {
  return {
    '/api/v1/system/status': {
      sharedAuthentication: false,
      csrfCookieName: 'director_fixture_csrf',
      videoGeneration: {
        enabled: false,
        available: false,
        authenticated: false,
        status: 'OFFLINE_FIXTURE',
        provider: 'kling',
        model: 'offline-fixture',
      },
    },
    '/api/v1/auth/me': { userId: 'director-fixture-user', username: 'director-fixture', role: 'USER' },
    '/api/v1/video-templates': [{
      id: 'synthetic-template',
      version: 'fixture-v1',
      status: 'active',
      name: 'Synthetic template',
      description: 'Offline fixture',
      minImages: 1,
      maxImages: 7,
      defaultSettings: { durationSeconds: 5, ratio: '9:16', sound: false, subtitles: false, smartStoryboard: false, continuityStrategy: 'explicit_cuts' },
      actionPresets: {},
      cameraPresets: {},
      tempoPresets: {},
    }],
    '/api/v1/site-style-profiles': [{
      id: 'synthetic-style',
      version: 'fixture-v1',
      status: 'active',
      name: 'Synthetic style',
      tone: 'Offline fixture',
    }],
    '/api/v1/motion-actions': [],
    '/api/v1/prompt-presets': [],
    '/api/v1/auth/preferences/prompt-confirmation': { automatic: false },
    '/api/v1/auth/preferences/video-learning': { enabled: false, feedbackCount: 0, scopeCount: 0, summary: 'Offline fixture', updatedAt: null },
    '/api/v1/admin/kling/elements': { items: [], pageNum: 1, pageSize: 100, total: 0, official: false },
  }
}

function json(route, value, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(value),
  })
}

async function runViewport({ browser, origin, width, height, evidenceDir }) {
  const context = await browser.newContext({
    viewport: { width, height },
    serviceWorkers: 'block',
  })
  const page = await context.newPage()
  const task = makeTask()
  const catalog = baseCatalogResponses()
  const requestLog = []
  const externalRequests = []
  const pageErrors = []
  let reloadStarted = false
  let recoveryTaskGets = 0
  let recoveryProductGets = 0

  page.on('pageerror', (error) => pageErrors.push(error.message))
  await context.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    requestLog.push({
      method: route.request().method(),
      path: requestUrl.pathname,
      postData: route.request().postData() ?? null,
    })
    if (requestUrl.origin !== origin && !['blob:', 'data:'].includes(requestUrl.protocol)) {
      externalRequests.push(requestUrl.origin)
      return route.abort()
    }
    if (!requestUrl.pathname.startsWith('/api/')) return route.continue()
    const method = route.request().method()

    if (method === 'GET' && catalog[requestUrl.pathname]) return json(route, catalog[requestUrl.pathname])
    if (method === 'GET' && requestUrl.pathname === '/api/v1/products/director-product-1') {
      if (reloadStarted) recoveryProductGets += 1
      return json(route, { id: 'director-product-1', current_version_id: 'director-product-version-1' })
    }
    if (method === 'GET' && requestUrl.pathname === '/api/v1/creative-workflow/tasks/director-task-1') {
      if (reloadStarted) recoveryTaskGets += 1
      return json(route, clone(task))
    }
    if (method === 'POST' && requestUrl.pathname === '/api/v1/products') {
      return json(route, { id: 'director-product-1' }, 201)
    }
    if (method === 'POST' && requestUrl.pathname === '/api/v1/creative-workflow/tasks') {
      task.status = 'DRAFT'
      task.state_version = 0
      return json(route, clone(task), 201)
    }
    if (method === 'POST' && requestUrl.pathname === '/api/v1/creative-workflow/tasks/director-task-1/commands') {
      const body = route.request().postDataJSON()
      assert.equal(body.expected_version, task.state_version, `command ${body.action} used a stale version`)
      const action = body.action
      if (action === 'analyze') {
        task.status = 'AWAITING_DIRECTION'
        task.snapshot.plan = {
          directions: [
            { id: 'A', scene: 'clean studio', behavior: 'standing garment display' },
            { id: 'B', scene: 'quiet street', behavior: 'walking garment display' },
            { id: 'C', scene: 'home interior', behavior: 'seated garment detail' },
          ],
        }
      } else if (action === 'select_direction') {
        task.status = 'PLAN_READY'
        task.snapshot.plan.selected_direction = body.direction_id
        task.snapshot.package = packageRecord({
          id: 'first-frame-package-1',
          revision: 3,
          parentId: null,
          shotId: 'FIRST_FRAME',
          purpose: 'FIRST_FRAME',
        })
      } else if (action === 'authorize') {
        task.snapshot.authorization = clone(body.authorization)
        if (body.authorization.scope === 'VIDEO_STORYBOARD') {
          assert(task.snapshot.selection, 'storyboard authorization requires selected first frame')
          const storyboardPackage = packageRecord({
            id: 'storyboard-package-1',
            revision: 4,
            parentId: 'first-frame-package-1',
            shotId: 'SHOT_01',
            purpose: 'VIDEO_STORYBOARD',
          })
          task.snapshot.storyboard.packages.SHOT_01 = storyboardPackage
          task.snapshot.authorization.package_id = storyboardPackage.package_id
        }
      } else if (action === 'generate') {
        if (body.shot_id === 'SHOT_01') {
          assert.equal(body.package_id, 'storyboard-package-1')
          task.status = 'STORYBOARD_REVIEW'
          task.snapshot.storyboard.candidates = [candidate({
            id: 'storyboard-candidate-1',
            packageId: 'storyboard-package-1',
            shotId: 'SHOT_01',
            authorizationId: task.snapshot.authorization.authorization_id,
          })]
        } else {
          assert.equal(body.package_id, 'first-frame-package-1')
          task.status = 'IMAGE_REVIEW'
          task.snapshot.candidates = [candidate({
            id: 'first-frame-candidate-1',
            packageId: 'first-frame-package-1',
            shotId: 'FIRST_FRAME',
            authorizationId: task.snapshot.authorization.authorization_id,
          })]
        }
        task.snapshot.execution_state = 'SUCCEEDED'
      } else if (action === 'review') {
        const storyboard = body.shot_id === 'SHOT_01'
        const candidates = storyboard ? task.snapshot.storyboard.candidates : task.snapshot.candidates
        const current = candidates.find((item) => item.candidate_id === body.candidate_id)
        assert(current, `missing candidate ${body.candidate_id}`)
        current.qualified = body.decision === 'QUALIFIED'
        const review = {
          candidate_id: body.candidate_id,
          reviewer_id: 'director-fixture-reviewer',
          decision: body.decision,
          qualification_scope: 'OFFLINE_SYNTHETIC_ONLY',
          reason: body.reason ?? null,
          ...(storyboard ? { shot_id: 'SHOT_01' } : {}),
        }
        if (storyboard) {
          task.snapshot.storyboard.latest_reviews.SHOT_01 = review
          delete task.snapshot.storyboard.selections.SHOT_01
        } else {
          task.snapshot.latest_review = review
          delete task.snapshot.selection
        }
      } else if (action === 'select') {
        if (body.shot_id === 'SHOT_01') {
          const current = task.snapshot.storyboard.candidates.find((item) => item.candidate_id === body.candidate_id)
          assert(current?.qualified, 'storyboard candidate must be qualified before selection')
          task.snapshot.storyboard.selections.SHOT_01 = {
            candidate_id: body.candidate_id,
            package_id: 'storyboard-package-1',
            shot_id: 'SHOT_01',
            batch_id: current.batch_id,
            item_id: current.item_id,
            output_id: current.output_id,
            synthetic: true,
          }
          task.snapshot.storyboard.shot_mappings.SHOT_01 = {
            shot_id: 'SHOT_01',
            package_id: 'storyboard-package-1',
            candidate_id: body.candidate_id,
            source_image_hash: 'source-image-hash-1',
            batch_id: current.batch_id,
            item_id: current.item_id,
            output_id: current.output_id,
            object_key: current.object_key,
          }
        } else {
          const current = task.snapshot.candidates.find((item) => item.candidate_id === body.candidate_id)
          assert(current?.qualified, 'first frame candidate must be qualified before selection')
          task.snapshot.selection = {
            candidate_id: body.candidate_id,
            package_id: 'first-frame-package-1',
            shot_id: 'FIRST_FRAME',
            batch_id: current.batch_id,
            item_id: current.item_id,
            output_id: current.output_id,
            synthetic: true,
          }
        }
      } else {
        assert.fail(`Unexpected director command: ${action}`)
      }
      task.state_version += 1
      return json(route, clone(task))
    }

    if (method === 'GET' && requestUrl.pathname === '/api/v1/tasks') return json(route, [])
    if (method === 'POST' && ['/api/v1/uploads', '/api/v1/video-tasks', '/api/v1/submission-recovery/query'].includes(requestUrl.pathname)) {
      assert.fail(`Production write reached director delivery fixture: ${requestUrl.pathname}`)
    }
    assert.fail(`Unexpected API request: ${method} ${requestUrl.pathname}`)
  })

  const result = {
    viewport: { width, height },
    passed: false,
    recoveryTaskGets: 0,
    recoveryProductGets: 0,
    requestCount: 0,
    forbiddenWrites: [],
  }

  try {
    await page.goto(origin)
    await page.getByRole('region', { name: '智能导演' }).waitFor()
    await page.getByRole('textbox', { name: '商品名称' }).fill('离线导演交付验收商品')
    await page.locator('input[type=file]').setInputFiles({
      name: 'director-front.png',
      mimeType: 'image/png',
      buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=', 'base64'),
    })
    await page.getByRole('button', { name: '创建任务并分析', exact: true }).click()
    await page.getByRole('region', { name: '方向差异对比' }).getByText('clean studio', { exact: true }).waitFor()

    await page.getByRole('button', { name: /A / }).click()
    await page.getByRole('region', { name: 'FIRST_FRAME 生产包证据' }).getByText('r3', { exact: true }).waitFor()
    await page.getByRole('button', { name: '授权 Fake 首帧', exact: true }).click()
    await page.getByRole('button', { name: '生成 Fake 首帧', exact: true }).click()
    const firstFrame = page.getByRole('region', { name: '首帧候选 1', exact: true })
    await firstFrame.waitFor()
    await firstFrame.getByRole('button', { name: '离线审核合格', exact: true }).click()
    await firstFrame.getByText('服务端审核：合格（仅离线范围）', { exact: true }).waitFor()
    await firstFrame.getByRole('button', { name: '选择离线首帧', exact: true }).click()
    await firstFrame.getByText('首帧选择：已选择（仅离线）', { exact: true }).waitFor()

    await page.getByRole('button', { name: '授权 Fake 分镜', exact: true }).click()
    await page.getByRole('region', { name: 'SHOT_01 生产包证据' }).getByText('r4', { exact: true }).waitFor()
    await page.getByRole('button', { name: '生成 Fake 分镜', exact: true }).click()
    const storyboard = page.getByRole('region', { name: '分镜候选 1', exact: true })
    await storyboard.waitFor()
    await storyboard.getByRole('button', { name: '离线审核合格', exact: true }).click()
    await storyboard.getByText('分镜选择：未选择', { exact: true }).waitFor()
    await storyboard.getByRole('button', { name: '选择离线分镜', exact: true }).click()
    await storyboard.getByText('分镜选择：已选择（仅离线）', { exact: true }).waitFor()

    const storageBeforeReload = await page.evaluate(() => localStorage.getItem('libtv:creative-project:v1:director-delivery-project'))
    assert(storageBeforeReload, 'project context was not persisted')
    const persisted = JSON.parse(storageBeforeReload)
    assert.equal(persisted.workflowContext.activeTaskId, 'director-task-1')
    assert.equal(persisted.metadata.directorRecovery.creative_task_id, 'director-task-1')
    assert.equal(persisted.metadata.directorRecovery.product_reference.source_sha256, 'source-image-hash-1')

    reloadStarted = true
    await page.reload()
    await page.getByRole('region', { name: '智能导演' }).waitFor()
    await page.getByText('已恢复服务端导演任务，审核、选择和当前版本来自服务端。', { exact: true }).waitFor()
    assert.equal(recoveryTaskGets > 0, true, 'reload did not recover the task through server GET')
    assert.equal(recoveryProductGets > 0, true, 'reload did not validate product through server GET')
    assert.equal(await page.locator('input[type=file]').count(), 1)
    assert.equal(await page.locator('input[type=file]').isDisabled(), true, 'recovery unexpectedly requires a new upload')
    await page.getByRole('button', { name: '视频工作室', exact: true }).click()
    await page.getByRole('region', { name: '导演固定视频准备' }).waitFor()

    const fixedPanel = page.getByRole('region', { name: '导演固定视频准备' })
    assert.equal(await fixedPanel.getAttribute('data-execution-mode'), 'director_fixed')
    assert.equal(await fixedPanel.getAttribute('data-provider-submission-allowed'), 'false')
    await fixedPanel.getByText('director-task-1', { exact: true }).waitFor()
    await fixedPanel.getByText('storyboard-package-1 · r4', { exact: true }).waitFor()
    await fixedPanel.getByText('SHOT_01', { exact: true }).waitFor()
    await fixedPanel.getByText('storyboard-candidate-1', { exact: true }).waitFor()
    await fixedPanel.getByText('source-image-hash-1', { exact: true }).waitFor()
    await fixedPanel.getByText('storyboard-candidate-1-output', { exact: true }).waitFor()

    const forbiddenWrites = requestLog.filter((request) =>
      request.method === 'POST'
      && ['/api/v1/uploads', '/api/v1/video-tasks', '/api/v1/submission-recovery/query'].includes(request.path),
    )
    assert.deepEqual(forbiddenWrites, [])
    assert.deepEqual(externalRequests, [])
    assert.deepEqual(pageErrors, [])
    result.passed = true
  } catch (error) {
    result.error = error instanceof Error ? error.message : String(error)
  } finally {
    result.recoveryTaskGets = recoveryTaskGets
    result.recoveryProductGets = recoveryProductGets
    result.requestCount = requestLog.length
    result.debug = await page.evaluate(() => ({
      url: location.href,
      bodyText: document.body.innerText.slice(0, 1200),
      persistedProject: localStorage.getItem('libtv:creative-project:v1:director-delivery-project'),
    }))
    result.forbiddenWrites = requestLog.filter((request) =>
      request.method === 'POST'
      && ['/api/v1/uploads', '/api/v1/video-tasks', '/api/v1/submission-recovery/query'].includes(request.path),
    )
    await page.screenshot({ path: resolve(evidenceDir, `director-delivery-${width}-final.png`), fullPage: true })
    await context.close()
  }
  return result
}

async function runRecoveryEdgeCases({ browser, origin, evidenceDir }) {
  const cases = []
  for (const scenario of ['invalid-reference-cleanup', 'network-failure-retention']) {
    const context = await browser.newContext({ viewport: { width: 1024, height: 768 }, serviceWorkers: 'block' })
    const page = await context.newPage()
    const projectKey = 'libtv:creative-project:v1:director-delivery-project'
    const recovery = {
      schemaVersion: 1,
      creative_task_id: 'director-task-1',
      product_reference: {
        product_id: 'director-product-1',
        product_version_id: 'director-product-version-1',
        source_sha256: 'source-image-hash-1',
      },
      planning_snapshot_index: { state_version: 9, package_revision: 4, saved_at: new Date().toISOString() },
    }
    await page.addInitScript(({ key, scenario, recovery }) => {
      const project = {
        id: 'director-delivery-project',
        assets: [],
        workflowContext: { activeTaskId: 'director-task-1', creativeTaskId: 'director-task-1' },
        metadata: {
          directorRecovery: recovery,
          directorPlanning: {
            brief: { productName: 'edge case', brandMode: 'generic', brandName: '', objective: '', audience: '', notes: '' },
            candidates: [],
            selectedDirectionId: 'A',
            productionPackage: null,
            handoff: null,
          },
        },
      }
      localStorage.setItem(key, JSON.stringify(project))
      window.__directorDeliveryScenario = scenario
    }, { key: projectKey, scenario, recovery })
    const errors = []
    const reads = []
    await context.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url())
      if (requestUrl.origin !== origin) return route.abort()
      if (!requestUrl.pathname.startsWith('/api/')) return route.continue()
      reads.push(requestUrl.pathname)
      if (requestUrl.pathname === '/api/v1/system/status') return json(route, { sharedAuthentication: false, csrfCookieName: 'director_fixture_csrf' })
      if (requestUrl.pathname === '/api/v1/auth/me') return json(route, { userId: 'director-fixture-user', username: 'fixture', role: 'USER' })
      if (requestUrl.pathname === '/api/v1/creative-workflow/tasks/director-task-1') {
        if (scenario === 'invalid-reference-cleanup') {
          return json(route, { detail: { code: 'TASK_NOT_FOUND', message: 'missing' } }, 404)
        }
        return route.abort('failed')
      }
      if (requestUrl.pathname === '/api/v1/products/director-product-1') return json(route, { id: 'director-product-1', current_version_id: 'director-product-version-1' })
      return json(route, [])
    })
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(origin)
    if (scenario === 'invalid-reference-cleanup') {
      await page.getByText('原导演任务已不存在，本地引用已清理。可以重新上传商品正面开始新任务。', { exact: true }).waitFor()
      const value = await page.evaluate((key) => localStorage.getItem(key), projectKey)
      const project = JSON.parse(value)
      assert.equal(project.metadata?.directorRecovery, undefined)
    } else {
      await page.getByText('任务恢复暂时失败，本地引用仍保留。请点击刷新后重试。', { exact: true }).waitFor()
      const value = await page.evaluate((key) => localStorage.getItem(key), projectKey)
      const project = JSON.parse(value)
      assert.equal(project.metadata.directorRecovery.creative_task_id, 'director-task-1')
    }
    assert.deepEqual(errors, [])
    cases.push({ scenario, passed: true, reads })
    await page.screenshot({ path: resolve(evidenceDir, `director-delivery-${scenario}.png`), fullPage: true })
    await context.close()
  }
  return cases
}

const server = await createFixtureServer(resolve(evidence, 'vite-cache'))
const browser = await chromium.launch({
  headless: true,
  ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}),
})
const report = {
  browser: browser.version(),
  sourceHashes: {},
  viewports: [],
  recoveryEdgeCases: [],
  externalRequests: [],
  limitations: [
    'This is an offline synthetic browser acceptance. It does not authorize Provider submission, paid generation, production writes, migrations, deployment, or service restart.',
  ],
}

try {
  for (const file of sourceFiles) {
    report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')
  }
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    try {
      const result = await runViewport({
        browser,
        origin: server.origin,
        ...viewport,
        evidenceDir: evidence,
      })
      report.viewports.push(result)
    } catch (error) {
      report.viewports.push({ viewport, passed: false, error: error instanceof Error ? error.message : String(error) })
    }
  }
  try {
    report.recoveryEdgeCases = await runRecoveryEdgeCases({ browser, origin: server.origin, evidenceDir: evidence })
  } catch (error) {
    report.recoveryEdgeCases = [{ passed: false, error: error instanceof Error ? error.message : String(error) }]
  }
  report.externalRequests = []
  assert.equal(report.viewports.length, 2)
  assert(report.viewports.every((item) => item.passed), JSON.stringify(report.viewports))
  assert(report.recoveryEdgeCases.length === 2 && report.recoveryEdgeCases.every((item) => item.passed), JSON.stringify(report.recoveryEdgeCases))
} finally {
  await writeFile(resolve(evidence, 'report.json'), JSON.stringify(report, null, 2))
  await browser.close()
  await server.server.close()
}

console.log(JSON.stringify(report, null, 2))
