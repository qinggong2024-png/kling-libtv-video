import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from '../../../../scripts/fixtures/video-studio-server.mjs'
import { createPageResponses } from '../../../../scripts/fixtures/ui-page-responses.mjs'

const root = fileURLToPath(new URL('../../../../', import.meta.url))
assert(process.env.PLAYWRIGHT_MODULE && process.env.UI_VIDEO_MIGRATION_REPORT_DIR && process.env.UI_STUDIO_MEDIA_DIR)
const reportDir = resolve(process.env.UI_VIDEO_MIGRATION_REPORT_DIR)
const evidenceRelative = relative(root, reportDir)
assert(evidenceRelative.startsWith('..') || isAbsolute(evidenceRelative), 'Evidence stays outside the checkout')
await mkdir(reportDir, { recursive: true })
const media = await readFile(resolve(process.env.UI_STUDIO_MEDIA_DIR, 'fixture-product.png'))
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'cache'), media })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const report = { scope: 'offline-video-desktop-migration-no-provider', capturedAt: new Date().toISOString(), cases: [], externalRequests: [], sourceHashes: {} }
for (const file of [
  'frontend/src/features/task-center/HomeView.tsx',
  'frontend/src/features/production/ProductionComposer.tsx',
  'frontend/src/features/production/ResultCard.tsx',
  'frontend/src/features/production/videoStudio.css',
  'frontend/src/features/production/studioRefinement.css',
]) report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')

try {
  for (const width of [1440, 1024]) {
    const sourceTasks = createPageResponses().get('/api/v1/tasks')
    fixture.state.tasks = sourceTasks.map((task, index) => ({
      ...structuredClone(task),
      id: `desktop-task-${index}`,
      title: `${index + 1} · 服装商品保真与关键质量人工审核_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789`,
    }))
    fixture.state.phase = 'AWAITING_FINAL_APPROVAL'
    fixture.state.mode = 'success'
    fixture.state.writes = []
    fixture.state.unexpected = []
    const context = await browser.newContext({ viewport: { width, height: width === 1024 ? 768 : 900 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await context.route('**/*', route => {
      const url = new URL(route.request().url())
      if (url.origin !== fixture.origin && !['blob:', 'data:'].includes(url.protocol)) {
        report.externalRequests.push(url.origin)
        return route.abort()
      }
      return route.continue()
    })
    const result = { width, checks: 0, passed: false }
    const check = (condition, message) => { assert(condition, message); result.checks += 1 }
    try {
      await page.goto(`${fixture.origin}/?view=make&pane=video`)
      await page.getByRole('combobox', { name: '视频模板', exact: true }).getByRole('option', { name: '服装多镜头展示', exact: true }).waitFor({ state: 'attached' })
      await page.locator('.attention-item').nth(2).waitFor()
      await page.locator('.result-card').nth(2).waitFor()
      result.layout = await page.evaluate(() => {
        const bounds = element => {
          const r = element.getBoundingClientRect()
          return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom }
        }
        return {
          overflow: document.documentElement.scrollWidth > innerWidth,
          sidebar: bounds(document.querySelector('.sidebar')),
          tasks: [...document.querySelectorAll('.attention-item')].map(item => ({
            card: bounds(item),
            content: bounds(item.querySelector('.attention-item-content')),
            button: bounds(item.querySelector('.primary-button')),
            text: item.querySelector('.attention-item-content').innerText,
          })),
          results: [...document.querySelectorAll('.result-card')].map(bounds),
          actions: [...document.querySelectorAll('.result-actions')].map(actions => ({
            bounds: bounds(actions),
            buttons: [...actions.querySelectorAll('button')].map(bounds),
          })),
        }
      })
      check(!result.layout.overflow, 'No horizontal page overflow')
      check(result.layout.sidebar.width === 240, 'Foundation sidebar remains 240px')
      for (const item of result.layout.tasks) {
        check(item.content.width >= 150, 'Task text keeps readable width')
        check(item.text.includes('商品保真与关键质量') && item.text.includes('ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'Task information remains present')
        check(item.button.x >= item.content.right - 1 || item.button.y >= item.content.bottom - 1, 'Task action does not cover text')
        check(item.button.right <= item.card.right, 'Task action fits its card')
      }
      if (width === 1440) {
        check(Math.abs(result.layout.tasks[0].card.y - result.layout.tasks[2].card.y) < 1, '1440 tasks remain horizontal')
        check(Math.abs(result.layout.results[0].y - result.layout.results[2].y) < 1, '1440 results retain three columns')
      } else {
        check(result.layout.tasks[1].card.y >= result.layout.tasks[0].card.bottom, '1024 tasks form a vertical list')
        check(result.layout.results[2].y >= result.layout.results[0].bottom, '1024 results use two columns')
      }
      for (const actions of result.layout.actions) {
        check(actions.buttons.every(button => button.x >= actions.bounds.x - 1 && button.right <= actions.bounds.right + 1), 'Result actions fit within the card')
      }
      await page.screenshot({ path: resolve(reportDir, `video-top-${width}.png`) })
      await page.getByRole('heading', { name: '需要你操作', exact: true }).scrollIntoViewIfNeeded()
      await page.screenshot({ path: resolve(reportDir, `video-tasks-${width}.png`) })
      await page.getByRole('heading', { name: '生成结果', exact: true }).scrollIntoViewIfNeeded()
      await page.screenshot({ path: resolve(reportDir, `video-results-${width}.png`) })
      check(fixture.state.writes.length === 0, 'Readability checks never create or review tasks')
      check(errors.length === 0, 'No browser runtime errors')
      check(fixture.state.unexpected.length === 0, 'No unhandled API calls')
      result.passed = true
    } catch (error) {
      result.failure = error.message
      await page.screenshot({ path: resolve(reportDir, `failure-${width}.png`), fullPage: true }).catch(() => {})
    } finally {
      report.cases.push(result)
      await context.close()
      console.log(`${result.passed ? 'PASS' : 'FAIL'} video-desktop-${width}: ${result.checks} checks${result.failure ? `, ${result.failure}` : ''}`)
    }
  }
  report.passed = report.cases.every(item => item.passed) && report.externalRequests.length === 0
  await writeFile(resolve(reportDir, 'report.json'), JSON.stringify(report, null, 2))
  assert(report.passed, 'Video desktop migration checks failed')
} finally {
  await browser.close()
  await fixture.server.close()
}
