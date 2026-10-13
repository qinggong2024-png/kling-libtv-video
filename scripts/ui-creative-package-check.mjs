import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const root = resolve(process.argv[2] || '.')
const evidence = resolve(process.env.CREATIVE_PACKAGE_EVIDENCE_DIR || '../creative-package-evidence')
assert(process.env.PLAYWRIGHT_MODULE, 'PLAYWRIGHT_MODULE is required')
assert(process.env.CREATIVE_PACKAGE_PYTHON, 'CREATIVE_PACKAGE_PYTHON is required')
const requireFrontend = createRequire(resolve(root, 'frontend/package.json'))
const { createServer } = await import(pathToFileURL(requireFrontend.resolve('vite')).href)
const { chromium } = requireFrontend(process.env.PLAYWRIGHT_MODULE)

// Windows clipboard reads use CRLF; only normalize this platform representation.
async function readClipboard(page) {
  return (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n')
}

async function trackClipboard(context) {
  await context.addInitScript(() => {
    const write = navigator.clipboard.writeText.bind(navigator.clipboard)
    navigator.clipboard.writeText = async text => {
      window.__creativePackageClipboardInput = text
      await write(text)
    }
  })
}

async function expectClipboard(page, expected) {
  assert.equal(await page.evaluate(() => window.__creativePackageClipboardInput), expected)
  assert.equal(await readClipboard(page), expected.replace(/\r\n/g, '\n'))
}

// Build the browser fixture with the real backend compiler and export adapter.
const fixtureProcess = spawnSync(process.env.CREATIVE_PACKAGE_PYTHON, ['-c', `
import json, uuid
from dataclasses import replace
from types import SimpleNamespace
from libtv_agent.creative.brand_dna import project_brand_dna
from libtv_agent.templates.site_style_profiles import SITE_STYLE_PROFILES
from libtv_agent.creative.workflow import compile_package, compile_storyboard_package, digest
from libtv_agent.services.creative_workflow import freeze_package_contract
from libtv_agent.services.creative_package_export import with_creative_package_exports
task_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
facts = {"product_id": str(task_id), "product_version_id": str(task_id), "facts_revision": 1,
         "source_asset_references": ["fixture/front.png"], "source_hash": "a" * 64}
locks = {"product_id": str(task_id), "source_hash": "a" * 64,
         "user_locks": {"selected_direction": "B", "shot_id": "FIRST_FRAME"}}
plan = {"revision": 2, "product_id": str(task_id), "product_version_id": str(task_id),
        "facts_revision": 1, "facts_snapshot_hash": digest(facts), "source_hash": "a" * 64,
        "locks": locks, "selected_direction": "B", "evidence": "FAKE_NOT_IMAGE_ANALYSIS",
        "directions": [{"id": "A", "scene": "plain studio", "behavior": "standing still"},
                       {"id": "B", "scene": "indoor room", "behavior": "seated casually"},
                       {"id": "C", "scene": "outdoor walkway", "behavior": "walking slowly"}],
        "claims": [{"claim_id": "front-source", "value": "front image available",
                    "source_fact_keys": ["source_asset_references"], "facts_revision": 1,
                    "evidence_kind": "OBSERVED_REFERENCE",
                    "confidence_basis": "synthetic fixture", "unknown_or_assumption": "back not observed"}]}
brand_a = replace(SITE_STYLE_PROFILES["geeksoutfit"], id="brand-a", name="Same brand name")
brand_b = replace(brand_a, id="brand-b", version="2.0.0", audience="Frozen configured audience")
brand = project_brand_dna(brand_b)
plan["brand_dna"] = brand
package = compile_package(task_id, plan, digest(locks), 1).model_dump(mode="json")
snapshot = {"plan": plan, "package": package, "facts_snapshot": facts, "product_version": facts, "brand_dna": brand,
            "trace": [], "candidates": [], "calls": 0, "cost_micros": 0, "total_calls": 0, "total_cost_micros": 0, "stopped": False,
            "asset": {"sha256": "a" * 64, "width": 64, "height": 96, "object_key": "fixture/front.png"},
            "storyboard": {"packages": {}}}
session = SimpleNamespace(add=lambda item: None)
freeze_package_contract(session, task_id, snapshot, package)
shot = compile_storyboard_package(task_id, plan, package, "synthetic-first-candidate", "SHOT_01").model_dump(mode="json")
snapshot["storyboard"]["packages"]["SHOT_01"] = shot
freeze_package_contract(session, task_id, snapshot, shot)
result = with_creative_package_exports({"id": str(task_id), "status": "PLAN_READY",
      "state_version": 2, "mode": "OFFLINE_FAKE_ONLY", "snapshot": snapshot})
result["browserBrandProfiles"] = [brand_a.to_public_dict(), brand_b.to_public_dict()]
print(json.dumps(result))
`], {
  cwd: root,
  env: { ...process.env, PYTHONPATH: resolve(root, 'backend/src') },
  encoding: 'utf8',
})
assert.equal(fixtureProcess.status, 0, fixtureProcess.stderr)
const fixture = JSON.parse(fixtureProcess.stdout)
assert.equal(Object.keys(fixture.creative_packages).length, 2, JSON.stringify(fixture.creative_package_errors))
await mkdir(evidence, { recursive: true })
await writeFile(resolve(evidence, 'backend-fixture.json'), JSON.stringify(fixture, null, 2))

const html = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Creative Package Acceptance</title></head>
<body><main id="root" style="max-width:1000px;margin:24px auto;padding:0 16px;min-width:0"></main>
<script type="module">
import React from 'react'
import { createRoot } from 'react-dom/client'
import { DirectorPackageEvidence } from '/src/features/director-studio/DirectorPlanningViews.tsx'
import { CreativePackageExportView } from '/src/features/director-studio/CreativePackageExportView.tsx'
import { DirectorStudio } from '/src/features/director-studio/DirectorStudio.tsx'
import '/src/styles.css'
import '/src/features/director-studio/directorStudio.css'
const workflow = await fetch('/fixture.json').then(response => response.json())
if (new URLSearchParams(location.search).has('legacy')) delete workflow.creative_packages
createRoot(document.getElementById('root')).render(new URLSearchParams(location.search).has('brandStudio') ? React.createElement('div', { className: 'image-center page-view' }, React.createElement(DirectorStudio)) : React.createElement('div', { className: 'director-studio' },
  ...['FIRST_FRAME', 'SHOT_01'].map(shotId => React.createElement('section', { key: shotId, 'aria-label': shotId + ' 创意交接' },
    React.createElement(CreativePackageExportView, { workflow, packageId: shotId === 'FIRST_FRAME' ? workflow.snapshot.package.package_id : workflow.snapshot.storyboard.packages[shotId].package_id },
      React.createElement(DirectorPackageEvidence, { workflow, shotId }))))))
</script></body></html>`
const server = await createServer({
  configFile: false, envFile: false, root: resolve(root, 'frontend'),
  cacheDir: resolve(evidence, 'vite-cache'), logLevel: 'error',
  server: { host: '127.0.0.1', port: 0 },
  plugins: [{
    name: 'creative-package-isolated-fixture',
    configureServer(vite) {
      vite.middlewares.use(async (req, res, next) => {
        const pathname = new URL(req.url, 'http://127.0.0.1').pathname
        if (pathname === '/fixture.json') {
          res.setHeader('Content-Type', 'application/json')
          return res.end(JSON.stringify(fixture))
        }
        if (pathname === '/') {
          res.setHeader('Content-Type', 'text/html; charset=utf-8')
          return res.end(await vite.transformIndexHtml('/', html))
        }
        next()
      })
    },
  }],
})
await server.listen()
const origin = server.resolvedUrls.local[0]
const browser = await chromium.launch({ headless: true, ...(process.env.DIRECTOR_BROWSER_PATH ? { executablePath: process.env.DIRECTOR_BROWSER_PATH } : {}) })
const report = { mode: 'OFFLINE_SYNTHETIC_ONLY', viewports: [], forbiddenRequests: [], pageErrors: [] }
try {
  for (const width of [1440, 1024, 768, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'], serviceWorkers: 'block' })
    await trackClipboard(context)
    const page = await context.newPage()
    page.on('pageerror', error => report.pageErrors.push(String(error)))
    await context.route('**/*', route => {
      if (!route.request().url().startsWith(origin) || route.request().method() !== 'GET') {
        report.forbiddenRequests.push(route.request().url())
        return route.abort()
      }
      return route.continue()
    })
    await page.goto(origin)
    const first = page.getByRole('region', { name: 'FIRST_FRAME 创意交接', exact: true })
    const shot = page.getByRole('region', { name: 'SHOT_01 创意交接', exact: true })
    await first.getByRole('button', { name: '复制完整 Creative Package', exact: true }).waitFor()
    assert.equal(await first.locator('details.creative-package-technical').getAttribute('open'), null)
    assert.equal(await first.getByRole('region', { name: 'FIRST_FRAME 生产包证据', exact: true }).isVisible(), false)
    assert(await first.getByText('Fake · 离线合成 · 不可交付。规划内容不等于已验证生产内容。', { exact: true }).isVisible())
    await first.getByRole('button', { name: '复制视频创作提案全文', exact: true }).click()
    await first.getByRole('status').filter({ hasText: '已复制' }).waitFor()
    const videoPrompt = fixture.creative_packages[fixture.snapshot.package.package_id].videoPrompt
    await expectClipboard(page, videoPrompt)
    assert(videoPrompt.includes('PROPOSED HUMAN HANDOFF') && videoPrompt.includes('FAKE SOURCE'))
    await first.getByRole('button', { name: '复制图片生成提示词全文', exact: true }).click()
    await first.getByRole('status').filter({ hasText: '已复制' }).waitFor()
    await expectClipboard(page, fixture.snapshot.package.prompt)
    await shot.getByRole('button', { name: '复制图片生成提示词全文', exact: true }).click()
    await shot.getByRole('status').filter({ hasText: '已复制' }).waitFor()
    await expectClipboard(page, fixture.snapshot.storyboard.packages.SHOT_01.prompt)
    await first.getByRole('button', { name: '复制完整 Creative Package', exact: true }).click()
    await first.getByRole('status').filter({ hasText: '已复制' }).waitFor()
    const copied = await readClipboard(page)
    assert(copied.includes('OFFLINE_SYNTHETIC_ONLY') && copied.includes(fixture.snapshot.package.prompt))
    const downloadEvent = page.waitForEvent('download')
    await first.getByRole('button', { name: '下载 Creative Package JSON', exact: true }).click()
    const download = await downloadEvent
    const target = resolve(evidence, `package-${width}.json`)
    await download.saveAs(target)
    assert.deepEqual(JSON.parse(await readFile(target, 'utf8')), fixture.creative_packages[fixture.snapshot.package.package_id])
    await page.reload()
    await first.getByRole('button', { name: '复制完整 Creative Package', exact: true }).waitFor()
    await first.getByRole('button', { name: '复制完整 Creative Package', exact: true }).focus()
    assert(await first.getByRole('button', { name: '复制完整 Creative Package', exact: true }).evaluate(element => element === document.activeElement))
    const layout = await page.evaluate(() => ({
      body: document.documentElement.scrollWidth,
      viewport: innerWidth,
      overflow: [...document.querySelectorAll('.creative-package-export button, .creative-package-export pre')].filter(element => {
        const rect = element.getBoundingClientRect()
        return rect.width && (rect.left < 0 || rect.right > innerWidth + 1)
      }).length,
    }))
    assert(layout.body <= layout.viewport + 1 && layout.overflow === 0, JSON.stringify(layout))
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: resolve(evidence, `package-${width}.png`), fullPage: true })
    await page.screenshot({ path: resolve(evidence, `package-${width}-viewport.png`) })
    await page.goto(`${origin}?legacy=1`)
    await first.getByText('Creative Package · 暂无可导出合同，未提供交接内容。', { exact: true }).waitFor()
    assert.equal(await first.getByRole('button', { name: '复制完整 Creative Package', exact: true }).count(), 0)
    report.viewports.push({ width, passed: true, copy: true, download: true, reload: true, legacy: true, layout })
    await context.close()
  }
  const failure = await browser.newContext()
  await failure.addInitScript(() => Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: async () => { throw new Error('denied') } },
  }))
  const page = await failure.newPage()
  await page.goto(origin)
  const first = page.getByRole('region', { name: 'FIRST_FRAME 创意交接', exact: true })
  await first.getByRole('button', { name: '复制完整 Creative Package', exact: true }).click()
  await first.getByRole('status').filter({ hasText: '复制失败' }).waitFor()
  assert(await first.getByRole('button', { name: '复制完整 Creative Package', exact: true }).isEnabled())
  report.clipboardFailure = true
  await failure.close()
  report.brandStudio = []
  for (const width of [1440, 1024, 768, 390]) {
    const context = await browser.newContext({ viewport: { width, height: ({390: 844, 768: 1024, 1024: 768})[width] ?? 900 }, permissions: ['clipboard-read', 'clipboard-write'], serviceWorkers: 'block' })
    await trackClipboard(context)
    const page = await context.newPage()
    const requests = []
    page.on('pageerror', error => report.pageErrors.push(String(error)))
    let task = structuredClone(fixture)
    const reply = (route, data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
    await context.route('**/api/v1/**', route => {
      const request = route.request()
      const pathname = new URL(request.url()).pathname
      requests.push(`${request.method()} ${pathname}`)
      if (pathname === '/api/v1/site-style-profiles') return reply(route, fixture.browserBrandProfiles)
      if (pathname === '/api/v1/system/status') return reply(route, { sharedAuthentication: false, csrfCookieName: 'fixture-csrf' })
      if (pathname === '/api/v1/auth/me') return reply(route, { userId: 'fixture-user', role: 'USER' })
      if (pathname === '/api/v1/products') return reply(route, { id: fixture.id }, 201)
      if (pathname === '/api/v1/creative-workflow/tasks') {
        const body = request.postData()
        assert(body.includes('name="brand_profile_id"\r\n\r\nbrand-b'))
        assert(body.includes('name="brand_profile_version"\r\n\r\n2.0.0'))
        task = { ...structuredClone(fixture), status: 'DRAFT', state_version: 0, creative_packages: {} }
        delete task.snapshot.package
        delete task.snapshot.plan
        delete task.snapshot.package_contracts
        delete task.snapshot.text_contract
        task.snapshot.storyboard = { packages: {}, candidates: [], selections: {} }
        return reply(route, task, 201)
      }
      if (pathname.endsWith('/commands')) {
        const command = request.postDataJSON()
        if (command.action === 'analyze') {
          task = { ...task, status: 'AWAITING_DIRECTION', state_version: 1 }
          task.snapshot.plan = { ...structuredClone(fixture.snapshot.plan), selected_direction: null }
        } else {
          assert.equal(command.action, 'select_direction')
          assert.equal(command.direction_id, 'B')
          task = structuredClone(fixture)
          task.snapshot.storyboard = { packages: {}, candidates: [], selections: {} }
        }
        return reply(route, task)
      }
      if (pathname === `/api/v1/creative-workflow/tasks/${fixture.id}`) return reply(route, task)
      report.forbiddenRequests.push(pathname)
      return route.abort()
    })
    await page.goto(`${origin}?brandStudio=1`)
    await page.getByRole('radio', { name: '选择品牌', exact: true }).check()
    const brandSelect = page.getByRole('combobox', { name: '品牌 必选', exact: true })
    await brandSelect.selectOption('brand-b')
    await page.getByLabel('Brand Creative DNA').getByText('目录建议 · 尚未绑定任务', { exact: true }).waitFor({ state: 'attached' })
    await page.locator('input[type=file]').setInputFiles({ name: 'front.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=', 'base64') })
    await page.getByRole('button', { name: '生成创意方向', exact: true }).click()
    const direction = page.getByRole('article', { name: '方向 B · 安静质感', exact: true })
    await direction.getByRole('button').click()
    assert.equal(requests.filter(value => value === 'POST /api/v1/creative-workflow/tasks/' + fixture.id + '/commands').length, 1, 'Card selection does not execute select_direction')
    await page.getByRole('button', { name: '确认方向：B · 安静质感', exact: true }).click()
    const packageStage = page.locator('.director-stage--package')
    const handoff = packageStage.getByRole('region', { name: '创意交接文档', exact: true }).first()
    await handoff.getByText('Frozen configured audience', { exact: true }).waitFor()
    const retainedBrandSelect = page.locator('.director-intake-fields select')
    assert(await retainedBrandSelect.isDisabled())
    assert.equal(await retainedBrandSelect.inputValue(), 'brand-b')
    assert.equal(await page.locator('html').evaluate(element => element.scrollWidth <= innerWidth + 1), true)
    assert.equal(await page.locator('.director-studio__workspace').evaluate(element => element.getBoundingClientRect().right <= innerWidth + 1), true)
    const technical = handoff.locator(':scope > details.creative-package-technical')
    assert.equal(await technical.getAttribute('open'), null)
    assert.equal(await packageStage.getByRole('region', { name: 'FIRST_FRAME 生产包证据', exact: true }).isVisible(), false)
    const visibleHeadings = await handoff.locator(':scope > section > h3, :scope > section > div > h3').allTextContents()
    assert.deepEqual(visibleHeadings, ['制作要求', '图片生成提示词', '视频创作提案', '镜头规划', '质量检查'])
    await page.evaluate(() => scrollTo(0, 0))
    const summaryBounds = await packageStage.getByRole('region', { name: '当前方案摘要', exact: true }).boundingBox()
    assert(summaryBounds.y >= 0 && summaryBounds.y < page.viewportSize().height, 'First screen leads with the package summary')
    await page.screenshot({ path: resolve(evidence, `handoff-first-screen-${width}.png`) })
    const callsBeforeCopy = requests.filter(value => value.startsWith('POST ')).length
    await handoff.getByRole('button', { name: '复制图片生成提示词全文', exact: true }).click()
    await expectClipboard(page, fixture.snapshot.package.prompt)
    await handoff.getByRole('button', { name: '复制视频创作提案全文', exact: true }).click()
    await expectClipboard(page, fixture.creative_packages[fixture.snapshot.package.package_id].videoPrompt)
    assert.equal(requests.filter(value => value.startsWith('POST ')).length, callsBeforeCopy, 'Copy does not execute workflow commands')
    await technical.locator(':scope > summary').click()
    assert(await packageStage.getByRole('region', { name: 'FIRST_FRAME 生产包证据', exact: true }).isVisible())
    await technical.locator(':scope > summary').click()
    assert.equal(await technical.getAttribute('open'), null)
    await page.screenshot({ path: resolve(evidence, `brand-studio-${width}.png`), fullPage: true })
    report.brandStudio.push({ width, passed: true, selectedId: 'brand-b', version: '2.0.0', requestCount: requests.length })
    await context.close()
  }
  assert.deepEqual(report.forbiddenRequests, [])
  assert.deepEqual(report.pageErrors, [])
  await writeFile(resolve(evidence, 'report.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report))
} finally {
  await browser.close()
  await server.close()
}
