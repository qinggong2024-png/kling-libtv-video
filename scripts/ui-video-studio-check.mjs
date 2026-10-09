import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve, relative, isAbsolute } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
assert(process.env.PLAYWRIGHT_MODULE, 'Set PLAYWRIGHT_MODULE to the installed Playwright package')
assert(process.env.UI_STUDIO_REPORT_DIR, 'Set UI_STUDIO_REPORT_DIR outside the checkout')
const reportDir = resolve(process.env.UI_STUDIO_REPORT_DIR)
assert(relative(root, reportDir).startsWith('..') || isAbsolute(relative(root, reportDir)), 'Evidence must be external')
await mkdir(reportDir, { recursive: true })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'vite-cache') })
const mediaPage = await browser.newPage()
await mediaPage.goto(fixture.origin)
const videoBytes = await mediaPage.evaluate(async () => {
  const canvas = document.createElement('canvas')
  canvas.width = 240; canvas.height = 320
  const ctx = canvas.getContext('2d')
  const stream = canvas.captureStream(20)
  const recorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp8' })
  const parts = []
  recorder.ondataavailable = (event) => parts.push(event.data)
  const done = new Promise((resolve) => { recorder.onstop = resolve })
  let frame = 0
  const draw = () => {
    ctx.fillStyle = '#eff0f2'; ctx.fillRect(0, 0, 240, 320)
    ctx.fillStyle = '#257d63'; ctx.fillRect(60 + Math.sin(frame++ / 8) * 12, 55, 120, 220)
  }
  draw()
  const timer = setInterval(draw, 50)
  recorder.start()
  await new Promise((resolve) => setTimeout(resolve, 1200))
  recorder.stop()
  await done
  clearInterval(timer)
  stream.getTracks().forEach((track) => track.stop())
  return Array.from(new Uint8Array(await new Blob(parts).arrayBuffer()))
})
fixture.state.video = Buffer.from(videoBytes)
await writeFile(resolve(reportDir, 'fixture-result.webm'), fixture.state.video)
await mediaPage.close()
const report = { scope: 'offline-video-studio-not-live-provider', capturedAt: new Date().toISOString(), sourceHead: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(), browserVersion: browser.version(), cases: [], externalRequests: [], sourceHashes: {} }
for (const file of ['frontend/src/features/production/ProductionComposer.tsx', 'frontend/src/features/production/MaterialCard.tsx', 'frontend/src/features/production/videoStudio.css', 'frontend/src/shared/components/studio/CreativeCanvas.tsx', 'frontend/src/shared/components/studio/TemplateSelector.tsx', 'frontend/src/shared/components/studio/SubjectDisclosure.tsx', 'frontend/src/shared/components/studio/Storyboard.tsx', 'frontend/src/shared/components/studio/SourceInspector.tsx', 'frontend/src/features/task-center/HomeView.tsx', 'frontend/src/shared/components/Media.tsx', 'frontend/src/app/App.tsx', 'scripts/ui-video-studio-check.mjs', 'scripts/fixtures/video-studio-server.mjs']) {
  report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')
}

async function run(width, mode = 'success') {
  fixture.state.mode = mode
  fixture.state.phase = 'QUEUED'
  fixture.state.tasks = []
  fixture.state.writes = []
  fixture.state.unexpected = []
  const context = await browser.newContext({ viewport: { width, height: ({ 390: 844, 768: 1024, 1024: 768, 1102: 884 })[width] ?? 900 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.setDefaultTimeout(15000)
  const result = { width, mode, passed: false }
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (url.origin === fixture.origin || url.protocol === 'blob:' || url.protocol === 'data:') return route.continue()
    report.externalRequests.push(url.origin)
    return route.abort()
  })
  try {
    await page.clock.install()
    await page.goto(`${fixture.origin}/studio/video`)
    const generate = page.getByRole('button', { name: '开始生成', exact: true })
    await page.getByRole('heading', { name: '视频制作', exact: true }).waitFor()
    assert(await generate.isDisabled())
    assert.equal(await page.locator('.composer .studio-canvas').count(), 0, 'No permanent empty source canvas')
    assert.equal(await page.locator('.composer .studio-storyboard').count(), 0, 'Empty uploader reserves no sequence area')
    assert.equal(await page.getByRole('heading', { name: '分镜序列', exact: true }).count(), 0)
    const subjectDisclosure = page.locator('.studio-subject-disclosure')
    const subjectSummary = subjectDisclosure.locator('summary')
    assert.equal(await subjectDisclosure.getAttribute('open'), null, 'Optional subject inputs start collapsed')
    assert(!(await page.getByRole('button', { name: '历史主体', exact: true }).isVisible()))
    await page.getByRole('combobox', { name: '视频模板', exact: true }).getByRole('option', { name: '服装多镜头展示', exact: true }).waitFor({ state: 'attached' })
    assert(await page.locator('.composer-submit-summary').evaluate((el) => el.getBoundingClientRect().width >= 200), 'Empty-state payment summary must not collapse')
    assert(await page.locator('.composer-submit-summary small').isVisible(), 'Payment consent stays visible')
    await page.screenshot({ path: resolve(reportDir, `empty-${width}.png`), fullPage: true })
    const bytes = await page.evaluate(() => {
      const canvas = document.createElement('canvas')
      canvas.width = 240; canvas.height = 320
      const ctx = canvas.getContext('2d')
      ctx.fillStyle = '#eff0f2'; ctx.fillRect(0, 0, 240, 320)
      ctx.fillStyle = '#257d63'
      ctx.beginPath(); ctx.moveTo(80, 55); ctx.lineTo(42, 88); ctx.lineTo(28, 158); ctx.lineTo(67, 168); ctx.lineTo(70, 279); ctx.lineTo(169, 279); ctx.lineTo(173, 168); ctx.lineTo(211, 158); ctx.lineTo(198, 88); ctx.lineTo(160, 55); ctx.closePath(); ctx.fill()
      ctx.fillStyle = '#eff0f2'; ctx.beginPath(); ctx.arc(120, 57, 24, 0, Math.PI); ctx.fill()
      return canvas.toDataURL('image/png').split(',')[1]
    })
    const png = Buffer.from(bytes, 'base64')
    fixture.state.media = png
    await writeFile(resolve(reportDir, 'fixture-product.png'), png)
    const files = [{ name: 'first.png', mimeType: 'image/png', buffer: png }, { name: 'second.png', mimeType: 'image/png', buffer: png }]
    await page.locator('.upload-panel input[type=file]').first().setInputFiles(files)
    await page.locator('.studio-storyboard .material-preview img').first().evaluate((img) => img.decode())
    assert.equal(await page.locator('.upload-panel--storyboard .studio-shot').count(), 2, 'Sorting belongs to the uploader')
    assert.equal(await page.locator('.composer-production-lane .studio-storyboard').count(), 0)
    await page.getByRole('button', { name: '前移分镜 2', exact: true }).click()
    assert.equal(await page.locator('.studio-shot__name').first().innerText(), 'second.png')
    // Reordering remains available by both pointer drag and keyboard controls.
    await page.locator('.studio-shot .material-card').first().dragTo(page.locator('.studio-shot .material-card').nth(1))
    assert.equal(await page.locator('.studio-shot__name').first().innerText(), 'first.png')
    await page.getByRole('button', { name: '前移分镜 2', exact: true }).click()
    const inspect = page.getByRole('button', { name: '查看图片 1 大图', exact: true })
    await inspect.focus()
    await page.keyboard.press('Enter')
    await page.getByRole('dialog').waitFor()
    await page.waitForFunction(() => document.querySelector('.studio-canvas__frame img')?.naturalWidth > 0)
    assert.equal(await page.locator('.studio-canvas header > div > span').count(), 0, 'Source inspection must not invent an output ratio')
    const zoom = page.getByRole('slider', { name: '画布缩放' })
    await zoom.fill('150')
    assert.equal(await page.locator('.studio-canvas output').innerText(), '150%')
    await page.getByRole('button', { name: '重置缩放', exact: true }).click()
    await page.screenshot({ path: resolve(reportDir, `source-inspector-${width}.png`) })
    await page.getByRole('button', { name: '打开大图', exact: true }).click()
    assert.equal(await page.getByRole('dialog').count(), 2)
    await page.screenshot({ path: resolve(reportDir, `source-inspection-${width}.png`) })
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('dialog').count(), 1)
    assert(await page.getByRole('button', { name: '打开大图', exact: true }).evaluate((el) => el === document.activeElement))
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('dialog').count(), 0)
    assert(await inspect.evaluate((el) => el === document.activeElement))
    result.onDemandInspectionAndFocus = true
    await page.locator('.upload-panel input[type=file]').first().setInputFiles({ name: 'delete-me.png', mimeType: 'image/png', buffer: png })
    await page.getByRole('button', { name: '删除图片 3', exact: true }).click()
    assert.equal(await page.locator('.studio-shot').count(), 2)
    await page.getByRole('combobox', { name: '视频模板', exact: true }).selectOption('second-template')
    await page.getByRole('button', { name: '查看配方', exact: true }).click()
    await page.getByRole('dialog').getByText('保持完整服装轮廓可见', { exact: true }).waitFor()
    await page.keyboard.press('Escape')
    await subjectSummary.focus()
    await page.keyboard.press('Enter')
    assert(await page.getByRole('button', { name: '历史主体', exact: true }).isVisible())
    await page.getByRole('button', { name: '历史主体', exact: true }).click()
    await page.getByRole('button', { name: '人物参考', exact: true }).click()
    await subjectSummary.click()
    assert.equal(await subjectDisclosure.getAttribute('open'), null)
    assert((await subjectSummary.innerText()).includes('人物参考'), 'Collapsed disclosure presents selected subject')
    await subjectSummary.click()
    assert.equal(await page.getByRole('button', { name: '人物参考', exact: true }).getAttribute('aria-pressed'), 'true', 'Collapsing preserves selected subject')
    await subjectSummary.click()
    result.subjectDisclosureKeepsSelection = true
    await page.getByRole('radio', { name: '自定义提示词', exact: true }).click()
    await page.getByPlaceholder('输入画面动作、镜头和节奏要求').fill('保持服装轮廓，缓慢转身，镜头稳定。')
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: resolve(reportDir, `custom-config-${width}.png`), fullPage: true })
    await page.getByRole('radio', { name: '自动化生成', exact: true }).click()
    await page.waitForFunction(() => !document.querySelector('.composer-submit-row > button')?.disabled)
    await page.evaluate(() => scrollTo(0, 0))
    result.configuredLayout = await page.evaluate(() => {
      const rect = (selector) => {
        const { x, y, width, height, bottom } = document.querySelector(selector).getBoundingClientRect()
        return { x, y, width, height, bottom }
      }
      return {
        viewport: { width: innerWidth, height: innerHeight },
        assets: rect('.composer-asset-lane'),
        production: rect('.composer-production-lane'),
        storyboard: rect('.studio-storyboard'),
        subject: rect('.studio-subject-disclosure'),
        results: rect('.studio-result-gallery'),
        submit: rect('.composer-submit-row > button'),
        submissionSummary: rect('.composer-submit-summary'),
        sourceRepresentations: document.querySelectorAll('.composer .material-preview img').length,
        permanentSourceCanvas: document.querySelectorAll('.composer .studio-canvas').length,
        resultCountsFit: (() => {
          const parent = document.querySelector('.composer-result-count .segmented-control').getBoundingClientRect()
          return [...document.querySelectorAll('.composer-result-count label')].every((label) => {
            const rect = label.getBoundingClientRect()
            return rect.left >= parent.left && rect.right <= parent.right && rect.width >= 44
          })
        })(),
      }
    })
    assert.equal(result.configuredLayout.sourceRepresentations, 2, 'One thumbnail per source')
    assert.equal(result.configuredLayout.permanentSourceCanvas, 0)
    assert(result.configuredLayout.resultCountsFit, 'All result-count options fit and remain touchable')
    assert(result.configuredLayout.submissionSummary.width >= 200, 'Payment summary has usable width')
    assert(await page.locator('.composer-submit-summary small').isVisible())
    assert(result.configuredLayout.submit.y >= Math.max(result.configuredLayout.assets.bottom, result.configuredLayout.production.bottom), 'Submission follows both preparation areas')
    assert(result.configuredLayout.production.y >= result.configuredLayout.assets.bottom, 'Creative configuration follows the material band, not a parallel form column')
    assert(Math.abs(result.configuredLayout.assets.width - result.configuredLayout.production.width) < 1, 'Material and creative bands span the same work area')
    assert(result.configuredLayout.subject.height <= 48, 'Collapsed subject does not reserve empty image slots')
    assert(result.configuredLayout.storyboard.height <= 190, 'Two-shot upload area remains compact')
    if (width >= 1280) {
      assert(result.configuredLayout.submit.bottom <= result.configuredLayout.viewport.height, 'Desktop submit visible without scrolling')
      assert(result.configuredLayout.results.y < result.configuredLayout.viewport.height, 'Result workspace begins in the desktop viewport')
    }
    await page.screenshot({ path: resolve(reportDir, `configured-${mode}-${width}.png`), fullPage: true })
    await page.evaluate(() => {
      const button = document.querySelector('.composer-submit-row > button')
      button.click(); button.click()
    })
    if (mode === 'unknown') {
      await page.getByText('提交结果未知', { exact: true }).waitFor()
      assert(await generate.isDisabled())
      await page.getByRole('button', { name: '安全核对', exact: true }).click()
      await page.getByText('仍无法安全判断结果', { exact: false }).waitFor()
      assert(await generate.isDisabled())
      assert.equal(fixture.state.writes.filter((write) => write.path === '/api/v1/video-tasks').length, 1)
      const create = fixture.state.writes.find((write) => write.path === '/api/v1/video-tasks')
      const recover = fixture.state.writes.find((write) => write.path === '/api/v1/submission-recovery/query')
      assert.equal(recover.payload.idempotencyKey, create.key)
      result.unknownGuard = true
    } else {
      const row = page.locator('.studio-task-card[data-task-id="fixture-video-1"]')
      await row.waitFor()
      assert.equal(await row.getAttribute('data-studio-status'), 'queued')
      await row.click()
      const drawer = page.getByRole('dialog')
      await drawer.waitFor()
      assert.equal(await page.locator('.composer .studio-canvas').count(), 0)
      assert.equal(new URL(page.url()).searchParams.get('task'), 'fixture-video-1')
      await page.reload()
      await drawer.waitFor()
      result.taskDeepLinkSurvivesReload = true
      result.statuses = ['queued']
      for (const [phase, label] of [['PREPARING', '正在准备生成'], ['GENERATING', '正在生成视频'], ['VALIDATING', '正在校验成品'], ['AWAITING_FINAL_APPROVAL', '待最终审核'], ['DELIVERABLE', '已完成']]) {
        fixture.state.phase = phase
        await page.clock.fastForward(4200)
        await drawer.getByText(label, { exact: true }).first().waitFor()
        result.statuses.push(phase)
      }
      const drawerPlay = drawer.getByRole('button', { name: '播放', exact: true }).first()
      await drawerPlay.click()
      assert.equal(await page.getByRole('dialog').count(), 2)
      await page.waitForFunction(() => document.querySelector('dialog video')?.currentTime > 0)
      await page.screenshot({ path: resolve(reportDir, `nested-video-${width}.png`) })
      await page.keyboard.press('Escape')
      assert.equal(await page.getByRole('dialog').count(), 1)
      assert(await drawerPlay.evaluate((element) => element === document.activeElement))
      result.nestedPreviewFocus = true
      await page.keyboard.press('Escape')
      assert.equal(await page.getByRole('dialog').count(), 0)
      await page.locator('.studio-result-gallery .result-card').waitFor()
      await page.getByRole('button', { name: '播放视频', exact: true }).click()
      const video = page.getByRole('dialog').locator('video')
      await video.waitFor()
      await page.waitForFunction(() => {
        const video = document.querySelector('dialog video')
        return video?.videoWidth === 240 && video?.videoHeight === 320 && video?.currentTime > 0
      })
      result.videoDecodedAndPlayed = true
      await page.keyboard.press('Escape')
      assert.equal(fixture.state.writes.filter((write) => write.path === '/api/v1/video-tasks').length, 1)
      const create = fixture.state.writes.find((write) => write.path === '/api/v1/video-tasks')
      assert.equal(create.payload.templateId, 'second-template')
      assert.deepEqual(create.payload.elementIds, ['fixture-character'])
      assert.equal(create.payload.paidSubmissionConsent, true)
      assert.equal(create.payload.storyboards.length, 2)
      assert(create.key && create.payload.clientTaskId)
      result.singleSubmission = true
      result.selectedTemplateAndCharacter = true
    }
    const geometry = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewport: innerWidth,
      uploader: (() => { const rect = document.querySelector('.upload-panel--storyboard').getBoundingClientRect(); return { width: rect.width, height: rect.height } })(),
    }))
    assert(geometry.documentWidth <= geometry.viewport, 'Page horizontal overflow')
    assert(geometry.uploader.width > 200, 'Uploader collapsed')
    assert.deepEqual(errors, [])
    assert.deepEqual(fixture.state.unexpected, [])
    result.geometry = geometry
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: resolve(reportDir, `${mode}-${width}.png`), fullPage: true })
    result.passed = true
  } catch (error) {
    result.failure = error.message
    result.pageErrors = errors
    await page.screenshot({ path: resolve(reportDir, `${mode}-${width}-failure.png`), fullPage: true }).catch(() => {})
  } finally {
    report.cases.push(result)
    await context.close()
    console.log(`${result.passed ? 'PASS' : 'FAIL'} ${mode}-${width}${result.failure ? `: ${result.failure}` : ''}`)
  }
}

async function runGuard(mode, width = 390) {
  fixture.state.mode = mode
  fixture.state.phase = 'QUEUED'
  fixture.state.tasks = []
  fixture.state.writes = []
  fixture.state.unexpected = []
  fixture.state.failAt = mode === 'batch-partial' ? 2 : null
  const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  const result = { width, mode, passed: false }
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (url.origin === fixture.origin || ['blob:', 'data:'].includes(url.protocol)) return route.continue()
    report.externalRequests.push(url.origin)
    return route.abort()
  })
  const file = (name) => ({ name, mimeType: 'image/png', buffer: fixture.state.media })
  const creates = () => fixture.state.writes.filter((write) => write.path === '/api/v1/video-tasks')
  try {
    await page.goto(`${fixture.origin}/studio/video`)
    await page.getByRole('heading', { name: '视频制作', exact: true }).waitFor()
    const generate = page.getByRole('button', { name: '开始生成', exact: true })
    if (mode === 'seven-shots') {
      await page.locator('.upload-panel input[type=file]').first().setInputFiles(Array.from({ length: 7 }, (_, index) => file(`shot-${index + 1}.png`)))
      const shots = page.locator('.upload-panel--storyboard .studio-shot')
      assert.equal(await shots.count(), 7)
      await shots.last().locator('img').evaluate((img) => img.decode())
      const grid = await page.locator('.studio-storyboard__track').evaluate((el) => ({
        scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
        rows: new Set([...el.children].map((child) => child.getBoundingClientRect().top)).size,
      }))
      assert(grid.scrollWidth <= grid.clientWidth, 'Seven shots must wrap without a scrolling strip')
      if (width < 800) assert(grid.rows > 1, 'Seven shots wrap on narrow screens')
      await page.getByRole('button', { name: '前移分镜 7', exact: true }).click()
      assert.equal(await page.locator('.studio-shot__name').nth(5).innerText(), 'shot-7.png')
      await page.evaluate(() => scrollTo(0, 0))
      await page.screenshot({ path: resolve(reportDir, `seven-uploaded-${width}.png`), fullPage: true })
      await page.getByRole('button', { name: '删除图片 6', exact: true }).click()
      assert.equal(await shots.count(), 6)
      assert(!(await page.locator('.studio-shot__name').allTextContents()).includes('shot-7.png'))
      assert.equal(creates().length, 0)
      result.uploadGrid = grid
    } else if (mode.startsWith('batch')) {
      const names = ['alpha_front.png', 'alpha_shot_1.png', 'beta_shot_1.png']
      if (mode !== 'batch-invalid') names.push('beta_front.png')
      await page.locator('.upload-panel input[type=file]').nth(1).setInputFiles(names.map(file))
      await page.getByText('批量识别', { exact: true }).waitFor()
      const inspect = page.getByRole('button', { name: '查看图片 1 大图', exact: true })
      await inspect.click()
      await page.getByRole('dialog').waitFor()
      await page.keyboard.press('Escape')
      assert(await page.getByRole('button', { name: '删除图片 1', exact: true }).isDisabled())
      assert.equal(await page.locator('.studio-shot .material-card').first().getAttribute('draggable'), 'false')
      result.batchInspectionWithoutMutation = true
      if (mode === 'batch-invalid') {
        assert(await generate.isDisabled())
        assert.equal(creates().length, 0)
        await page.getByRole('button', { name: '退出批量，编辑当前组', exact: true }).click()
        await page.waitForFunction(() => !document.querySelector('.composer-submit-row > button')?.disabled)
        assert(await generate.isEnabled())
      } else {
        await generate.click()
        await page.getByText('离线合成：素材未通过校验', { exact: true }).waitFor()
        assert.equal(fixture.state.tasks.length, 1)
        await page.getByText('当前预览：beta · 批量 1 组', { exact: true }).waitFor()
        fixture.state.failAt = null
        await generate.click()
        await page.waitForFunction(() => document.querySelectorAll('.studio-task-card').length === 2)
        assert.equal(fixture.state.tasks.length, 2)
        assert.equal(creates().length, 3)
        assert(creates()[0].payload.title.startsWith('alpha'))
        assert(creates()[1].payload.title.startsWith('beta'))
        assert(creates()[2].payload.title.startsWith('beta'))
        result.noDuplicateSuccessfulGroups = true
      }
    } else {
      await page.locator('.upload-panel input[type=file]').first().setInputFiles([file('product.png')])
      if (mode === 'no-template') {
        await page.getByRole('combobox', { name: '视频模板', exact: true }).getByRole('option', { name: '暂无可用模板', exact: true }).waitFor({ state: 'attached' })
        assert(await generate.isDisabled())
        assert.equal(creates().length, 0)
      } else if (mode === 'catalog-failure') {
        await page.getByText('离线合成：模板读取失败', { exact: true }).waitFor()
        assert(await generate.isDisabled())
        fixture.state.mode = 'success'
        await page.getByRole('button', { name: '重新读取', exact: true }).click()
        await page.waitForFunction(() => !document.querySelector('.composer-submit-row > button')?.disabled)
        assert.equal(creates().length, 0)
        result.catalogRecovery = true
      } else {
        await generate.click()
        await page.getByText('离线合成：素材未通过校验', { exact: true }).waitFor()
        assert(await generate.isEnabled())
        assert.equal(fixture.state.tasks.length, 0)
        fixture.state.mode = 'success'
        await generate.click()
        const row = page.locator('.studio-task-card')
        await row.waitFor()
        fixture.state.phase = 'ACTION_REQUIRED'
        await row.click()
        await page.getByRole('dialog').getByText('任务需要处理', { exact: true }).first().waitFor()
        await page.keyboard.press('Escape')
        assert.equal(creates().length, 2)
        result.definiteFailureAllowsCorrection = true
      }
    }
    assert.deepEqual(errors, [])
    assert.deepEqual(fixture.state.unexpected, [])
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: resolve(reportDir, `${mode}-${width}.png`), fullPage: true })
    result.passed = true
  } catch (error) {
    result.failure = error.message
    await page.screenshot({ path: resolve(reportDir, `${mode}-${width}-failure.png`), fullPage: true }).catch(() => {})
  } finally {
    report.cases.push(result)
    await context.close()
    console.log(`${result.passed ? 'PASS' : 'FAIL'} ${mode}-${width}${result.failure ? `: ${result.failure}` : ''}`)
  }
}
try {
  for (const width of [1440, 1102, 1024, 768, 390]) await run(width)
  await run(390, 'unknown')
  for (const mode of ['no-template', 'catalog-failure', 'batch-invalid', 'batch-partial', 'rejected']) await runGuard(mode)
  for (const width of [1440, 390]) await runGuard('seven-shots', width)
  report.passed = report.cases.every((test) => test.passed) && report.externalRequests.length === 0
  await writeFile(resolve(reportDir, 'result.json'), JSON.stringify(report, null, 2))
  assert(report.passed, 'Video Studio fixture acceptance failed')
} finally {
  await browser.close()
  await fixture.server.close()
}
