import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'
import { createPageResponses } from './fixtures/ui-page-responses.mjs'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
assert(process.env.PLAYWRIGHT_MODULE && process.env.CREATIVE_SHELL_REPORT_DIR && process.env.UI_STUDIO_MEDIA_DIR)
const reportDir = resolve(process.env.CREATIVE_SHELL_REPORT_DIR)
const evidenceRelative = relative(root, reportDir)
assert(evidenceRelative.startsWith('..') || isAbsolute(evidenceRelative), 'Evidence must be outside the checkout')
await mkdir(reportDir, { recursive: true })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const media = await readFile(resolve(process.env.UI_STUDIO_MEDIA_DIR, 'fixture-product.png'))
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'vite-cache'), media })
const browser = await chromium.launch({ channel: process.env.UI_BROWSER_CHANNEL || 'chrome', headless: true })
const report = { scope: 'isolated-ui-only-no-provider', browserVersion: browser.version(), cases: [], blockedExternalRequests: [], sourceHashes: {} }
for (const file of [
  'frontend/src/app/App.tsx', 'frontend/src/app/AppShell.tsx', 'frontend/src/styles.css',
  'frontend/src/features/creative-workspace/CreativeWorkspaceView.tsx',
  'frontend/src/features/director-studio/directorStudio.css',
  'frontend/src/features/image-studio/ImageStudio.tsx',
]) report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')

try {
  for (const width of [1440, 1024, 768, 390]) {
    const height = width === 1024 ? 768 : width === 768 ? 1024 : width === 390 ? 844 : 900
    const context = await browser.newContext({
      viewport: { width, height },
      reducedMotion: width === 390 ? 'reduce' : 'no-preference', serviceWorkers: 'block',
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const result = { width, passed: false, layouts: {} }
    await context.route('**/*', route => {
      const url = new URL(route.request().url())
      if (url.origin !== fixture.origin && !['blob:', 'data:'].includes(url.protocol)) {
        report.blockedExternalRequests.push(url.origin)
        return route.abort()
      }
      // Use the real provider composition, while every API stays on the isolated fixture.
      if (route.request().isNavigationRequest() && url.pathname === '/') return route.fulfill({
        contentType: 'text/html',
        body: '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Creative OS isolated UI verification</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>',
      })
      return route.continue()
    })
    const layout = async (name) => {
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: no horizontal page overflow at ${width}`)
      result.layouts[name] = await page.evaluate(() => ({
        viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        directorColumns: document.querySelector('.director-studio__grid')
          ? getComputedStyle(document.querySelector('.director-studio__grid')).gridTemplateColumns : null,
      }))
      await page.screenshot({ path: resolve(reportDir, `${name}-${width}.png`), fullPage: true })
    }
    try {
      fixture.state.tasks = []
      await page.goto(`${fixture.origin}/?view=make&pane=workspace&project=ui2-fixture`)
      await page.getByRole('heading', { name: 'Creative Project', exact: true }).waitFor()
      assert.equal(await page.getByRole('region', { name: '当前项目' }).count(), 0, 'Workspace does not duplicate the project context entry')
      assert(!(await page.locator('.home-view').isVisible()), 'Workspace does not stack above a visible Video Studio')
      const nav = page.getByRole('navigation', { name: width > 820 ? '制作导航' : '移动端主导航', exact: true })
      assert.equal(await nav.getByRole('button', { name: '图片工作室', exact: true }).count(), 1)
      assert.equal(await page.locator('.product-nav, .mobile-product-nav, .legacy-nav').count(), 0)
      await layout('workspace')
      const next = page.getByRole('button', { name: '开始导演规划', exact: true })
      assert((await next.boundingBox()).y < height, 'Next action is visible in the first viewport')
      await page.getByRole('button', { name: '编辑项目名称', exact: true }).click()
      const editor = page.getByRole('dialog', { name: '项目设置', exact: true })
      await editor.waitFor()
      const longName = '创意项目ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.repeat(2)
      await editor.getByLabel('项目名称', { exact: true }).fill(longName)
      await editor.getByRole('button', { name: '保存项目名称', exact: true }).click()
      await editor.waitFor({ state: 'hidden' })
      assert(await page.getByRole('button', { name: '编辑项目名称', exact: true }).evaluate(el => el === document.activeElement))
      await layout('workspace-long-name')
      await next.click()
      await page.getByRole('region', { name: '智能导演', exact: true }).waitFor()
      assert(new URL(page.url()).searchParams.get('project') === 'ui2-fixture')
      assert.equal(await page.locator('.director-studio__grid').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length), width >= 1280 ? 3 : width > 760 ? 2 : 1)
      for (const index of await page.locator('.director-panel__index').all()) assert.equal(await index.evaluate(el => getComputedStyle(el).whiteSpace), 'nowrap')
      await layout('director-empty')
      const director = page.getByRole('region', { name: '智能导演', exact: true })
      await director.getByRole('textbox', { name: '商品名称', exact: true }).fill('离线服装展示输入')
      await director.locator('input[type=file]').setInputFiles({ name: 'fixture-product.png', mimeType: 'image/png', buffer: media })
      assert(await director.getByRole('img', { name: '商品正面预览', exact: true }).evaluate(img => img.complete && img.naturalWidth > 0))
      assert(await director.getByRole('button', { name: '创建任务并分析', exact: true }).isEnabled())
      await layout('director-input')
      await page.goBack()
      await page.getByRole('heading', { name: longName, exact: true }).waitFor()
      await page.goForward()
      await director.waitFor()
      await nav.getByRole('button', { name: '视频工作室', exact: true }).click()
      await page.locator('.home-view').waitFor({ state: 'visible' })
      assert.equal(await page.locator('.image-center[hidden]').count(), 1, 'Image Studio stays mounted offscreen for polling and notifications')
      assert.equal(await nav.getByRole('button', { name: '视频工作室', exact: true }).getAttribute('aria-current'), 'page')
      await layout('video')
      for (const [query, selector] of [
        ['view=images', '.image-center'], ['view=make', '.home-view'],
        ['view=records', '.records-overview'], ['view=library', '.content-library-view'],
        ['view=make&pane=projects', '.creative-workspace-view'], ['view=make&pane=memory', '.creative-workspace-view'],
      ]) {
        await page.goto(`${fixture.origin}/?${query}`)
        await page.locator(selector).waitFor({ state: 'visible' })
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      }
      await page.goto(`${fixture.origin}/?view=images&pane=director`)
      await director.waitFor()
      assert.equal(await nav.getByRole('button', { name: '图片工作室', exact: true }).getAttribute('aria-current'), 'page', 'Director remains an Image Studio mode')
      await page.getByRole('button', { name: '批量创作', exact: true }).click()
      await page.locator('.image-center-create').waitFor({ state: 'visible' })
      await layout('image')
      assert.deepEqual(errors, [])
      result.passed = true
    } catch (error) {
      result.error = error.stack
      await page.screenshot({ path: resolve(reportDir, `failure-${width}.png`), fullPage: true })
    } finally {
      report.cases.push(result)
      await context.close()
    }
  }
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' })
  const page = await context.newPage()
  // Many rows allow a meaningful records scroll restoration assertion.
  const baseTask = createPageResponses().get('/api/v1/tasks')[1]
  fixture.state.tasks = Array.from({ length: 25 }, (_, index) => ({
    ...structuredClone(baseTask), id: `ui2-task-${index}`, title: `UI2 isolated task ${index}`,
  }))
  fixture.state.phase = 'GENERATING'
  await page.goto(`${fixture.origin}/?view=records`)
  await page.locator('.task-table-row').nth(20).waitFor()
  await page.locator('.task-table-row').nth(20).scrollIntoViewIfNeeded()
  const scroll = await page.evaluate(() => scrollY)
  assert(scroll > 100)
  await page.locator('.task-table-row').nth(20).click()
  await page.locator('.foundation-drawer').waitFor({ state: 'visible' })
  assert.equal(new URL(page.url()).searchParams.get('task'), 'ui2-task-20')
  await page.keyboard.press('Escape')
  await page.locator('.foundation-drawer').waitFor({ state: 'hidden' })
  await page.waitForFunction(expected => Math.abs(scrollY - expected) < 4, scroll)
  await page.goto(`${fixture.origin}/?task=ui2-task-20`)
  await page.locator('.foundation-drawer').waitFor({ state: 'visible' })
  await page.screenshot({ path: resolve(reportDir, 'task-deep-link.png') })
  report.cases.push({ name: 'task-deep-link-and-records-scroll', passed: true })
  await context.close()
  assert.equal(fixture.state.writes.length, 0, 'Shell verification never submits production tasks')
} catch (error) {
  report.cases.push({ name: 'runtime', passed: false, error: error.stack })
} finally {
  await browser.close()
  await fixture.server.close()
  await writeFile(resolve(reportDir, 'report.json'), JSON.stringify(report, null, 2))
}
console.log(JSON.stringify({ cases: report.cases.map(({ width, name, passed, error }) => ({ width, name, passed, error })), evidence: reportDir }, null, 2))
if (report.cases.some(result => !result.passed)) process.exitCode = 1
