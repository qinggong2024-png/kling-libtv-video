import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createStudioFixtureServer } from './fixtures/video-studio-server.mjs'

const root = fileURLToPath(new URL('..', import.meta.url))
assert(process.env.PLAYWRIGHT_MODULE && process.env.DIRECTOR_MOBILE_REPORT_DIR && process.env.UI_STUDIO_MEDIA_DIR)
const reportDir = resolve(process.env.DIRECTOR_MOBILE_REPORT_DIR)
const outside = relative(root, reportDir)
assert(outside.startsWith('..') || isAbsolute(outside), 'Evidence stays outside the checkout')
await mkdir(reportDir, { recursive: true })
const media = await readFile(resolve(process.env.UI_STUDIO_MEDIA_DIR, 'fixture-product.png'))
const fixture = await createStudioFixtureServer({ cacheDir: resolve(reportDir, 'cache'), media })
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
const browser = await chromium.launch({ channel: process.env.UI_BROWSER_CHANNEL || 'chrome', headless: true })
const report = {
  scope: 'sprint8-p05-director-action-only-offline',
  capturedAt: new Date().toISOString(), browserVersion: browser.version(),
  cases: [], externalRequests: [], writes: [], sourceHashes: {},
}
for (const file of [
  'frontend/src/features/director-studio/directorStudio.css',
  'frontend/src/features/director-studio/DirectorStudio.tsx',
  'frontend/src/app/App.tsx', 'frontend/src/app/AppShell.tsx', 'frontend/src/styles.css',
  'scripts/ui-director-mobile-check.mjs',
]) report.sourceHashes[file] = createHash('sha256').update(await readFile(resolve(root, file))).digest('hex')

try {
  for (const [width, height] of [[390, 844], [390, 664], [1024, 768], [1440, 900]]) {
    const context = await browser.newContext({
      viewport: { width, height }, serviceWorkers: 'block',
      reducedMotion: width === 390 ? 'reduce' : 'no-preference',
    })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    const errors = []
    const consoleErrors = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    await context.route('**/*', route => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.origin !== fixture.origin && !['blob:', 'data:'].includes(url.protocol)) {
        report.externalRequests.push(url.origin)
        return route.abort()
      }
      if (!['GET', 'HEAD'].includes(request.method())) {
        report.writes.push({ path: url.pathname, method: request.method() })
        return route.abort()
      }
      if (request.isNavigationRequest() && url.pathname === '/') return route.fulfill({
        contentType: 'text/html',
        body: '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Director mobile offline check</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>',
      })
      return route.continue()
    })
    const result = { width, height, passed: false, checks: 0, layouts: [] }
    const check = (condition, message) => { assert(condition, message); result.checks += 1 }
    try {
      await page.goto(`${fixture.origin}/?view=images&pane=director`)
      const director = page.getByRole('region', { name: '智能导演', exact: true })
      await director.waitFor()
      await page.locator('.page-loading').waitFor({ state: 'hidden' })
      const action = director.getByRole('button', { name: '生成创意方向', exact: true })
      const nav = page.getByRole('navigation', { name: width === 390 ? '移动端主导航' : '制作导航', exact: true })
      const advancedEntry = async () => {
        const entry = await director.locator('.director-brief-details summary').evaluate(summary => {
          const bounds = summary.getBoundingClientRect()
          return {
            bottom: bounds.bottom,
            hit: summary.contains(document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)),
          }
        })
        check(entry.bottom <= (await action.boundingBox()).y && entry.hit, 'Advanced settings entry remains unobscured above the action')
      }
      const geometry = async (state) => {
        // Short viewports use document scrolling so the action cannot cover input controls.
        if (width === 390 && height < 780) await action.scrollIntoViewIfNeeded()
        const layout = await action.evaluate(button => {
          const rect = element => {
            const { x, y, width, height, bottom } = element.getBoundingClientRect()
            return { x, y, width, height, bottom }
          }
          const bounds = button.getBoundingClientRect()
          const visibleNav = document.querySelector('.mobile-nav')
          return {
            action: rect(button),
            nav: visibleNav && getComputedStyle(visibleNav).display !== 'none' ? rect(visibleNav) : null,
            position: getComputedStyle(button.parentElement).position,
            hit: button.contains(document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)),
            scrollY, viewport: innerHeight, scrollWidth: document.documentElement.scrollWidth,
          }
        })
        result.layouts.push({ state, ...layout })
        check(layout.scrollWidth <= width, `${state}: no horizontal page overflow`)
        if (width === 390) {
          check(layout.action.y >= 56 && layout.action.bottom <= layout.nav.y, `${state}: full action fits between header and navigation`)
          check(layout.hit, `${state}: action receives the pointer instead of the navigation`)
        } else check(layout.position !== 'sticky', `${state}: desktop action keeps its normal layout`)
        await page.screenshot({ path: resolve(reportDir, `${state}-${width}-${height}.png`) })
      }
      check(await action.isDisabled(), 'Missing input keeps analysis disabled')
      await geometry('empty')
      if (width === 390 && height === 844) await advancedEntry()
      await director.locator('input[type=file]').setInputFiles({ name: 'fixture-product.png', mimeType: 'image/png', buffer: media })
      await page.waitForFunction(() => {
        const image = document.querySelector('.director-upload img')
        return image?.complete && image.naturalWidth > 0
      })
      check(await action.isEnabled(), 'Local product input enables the existing action')
      await geometry('uploaded')
      if (width === 390 && height === 844) await advancedEntry()
      if (width === 390) {
        await action.click({ trial: true })
        check(await action.isEnabled(), 'Trial hit testing leaves analysis unsubmitted')
        await director.locator('.director-choice input[type=radio]').nth(1).check()
        check(await action.isDisabled(), 'Brand selection retains its existing required-input condition')
        await geometry('brand-required')
        await director.locator('.director-choice input[type=radio]').first().check()
        await director.locator('.director-brief-details summary').click()
        await geometry('advanced-open')
        await page.evaluate(() => scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }))
        check(await page.evaluate(() => scrollY > 100), 'Advanced input remains vertically scrollable')
        await action.scrollIntoViewIfNeeded()
        await geometry('advanced-scrolled')
        await action.click({ trial: true })
        const notes = director.getByRole('textbox', { name: /创作备注/ })
        await notes.scrollIntoViewIfNeeded()
        await notes.fill('Offline mobile action check')
        check(await notes.inputValue() === 'Offline mobile action check', 'Advanced input stays editable')
        await nav.getByRole('button', { name: '图片工作室', exact: true }).click()
        await page.getByRole('heading', { name: '图片工作室', level: 1, exact: true }).waitFor()
        await nav.getByRole('button', { name: '导演台', exact: true }).click()
        await director.waitFor()
        await action.scrollIntoViewIfNeeded()
        await geometry('navigation-return')
      }
      check(errors.length === 0, 'No unhandled browser errors')
      result.passed = true
    } catch (error) {
      result.error = error.stack
      result.pageErrors = errors
      result.consoleErrors = consoleErrors
      await page.screenshot({ path: resolve(reportDir, `failure-${width}-${height}.png`), fullPage: true })
    } finally {
      report.cases.push(result)
      await context.close()
    }
  }
  assert.deepEqual(report.externalRequests, [])
  assert.deepEqual(report.writes, [])
  assert.deepEqual(fixture.state.writes, [])
} finally {
  await browser.close()
  await fixture.server.close()
  report.sourcesUnchanged = true
  for (const [file, hash] of Object.entries(report.sourceHashes)) {
    if (createHash('sha256').update(await readFile(resolve(root, file))).digest('hex') !== hash) report.sourcesUnchanged = false
  }
  report.passed = report.sourcesUnchanged && report.cases.length === 4 && report.cases.every(result => result.passed)
  await writeFile(resolve(reportDir, 'report.json'), JSON.stringify(report, null, 2))
}
console.log(JSON.stringify({
  passed: report.passed, sourcesUnchanged: report.sourcesUnchanged,
  cases: report.cases.map(({ width, height, passed, checks, error }) => ({ width, height, passed, checks, error })),
  evidence: reportDir,
}, null, 2))
if (!report.passed) process.exitCode = 1
