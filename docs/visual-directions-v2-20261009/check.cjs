const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const { createHash } = require('node:crypto')

async function main() {
  assert(process.env.PLAYWRIGHT_MODULE, 'Set PLAYWRIGHT_MODULE to the installed entry')
  assert(process.env.PREVIEW_REPORT_DIR, 'Set PREVIEW_REPORT_DIR outside either checkout')
  const { chromium } = require(process.env.PLAYWRIGHT_MODULE)
  const root = path.resolve(process.env.PREVIEW_ROOT || __dirname)
  const out = path.resolve(process.env.PREVIEW_REPORT_DIR)
  assert(!out.startsWith(root + path.sep), 'Evidence must not be saved in source')
  await fs.mkdir(out, { recursive: true })
  const report = { scope: 'independent-visual-direction-prototypes', cases: [], errors: [], externalRequests: [], sourceHashes: {} }
  for (const file of ['preview.js', 'refinement.js', 'preview.css', 'icons.js', 'index.html', 'direction-b.html', 'direction-c.html']) {
    report.sourceHashes[file] = createHash('sha256').update(await fs.readFile(path.join(root, file))).digest('hex')
  }
  const browser = await chromium.launch({ headless: true })
  report.browser = browser.version()
  try {
    for (const [direction, file] of [['a', 'index.html'], ['b', 'direction-b.html'], ['c', 'direction-c.html']]) {
      for (const [width, height] of [[1440, 900], [1102, 900], [1024, 768], [768, 1024], [390, 844]]) {
        const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' })
        const page = await context.newPage()
        page.on('pageerror', error => report.errors.push(error.message))
        page.on('request', request => {
          if (/^https?:/.test(request.url())) report.externalRequests.push(request.url())
        })
        await page.goto(pathToFileURL(path.join(root, file)).href)
        await page.waitForFunction(() => document.querySelectorAll('.asset-image img').length === 2
          && [...document.images].filter(image => image.getAttribute('src')).every(image => image.complete && image.naturalWidth > 0))
        assert.equal(await page.locator('h1').innerText(), '视频制作')
        await page.locator('#acknowledge').evaluate(el => { el.checked = false; el.dispatchEvent(new Event('change')) }); assert(await page.locator('#submit').isDisabled())
        const geometry = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          viewport: innerWidth,
          submit: document.querySelector('#submit').getBoundingClientRect().toJSON(),
          clipped: [...document.querySelectorAll('button, select, .asset-footer')].filter(el =>
            el.offsetWidth && el.scrollWidth > el.clientWidth + 3).map(el => el.textContent.trim()),
        }))
        assert(geometry.scroll <= geometry.viewport + 1, `Overflow ${direction}/${width}`)
        assert.deepEqual(geometry.clipped, [], `Clipped labels ${direction}/${width}`)
        if (width === 1440 && direction === 'c') assert(await page.locator('.asset-area .next-step').evaluate(el => el.getBoundingClientRect().bottom <= innerHeight))
        if (width === 1440 && direction !== 'c') assert(geometry.submit.bottom <= height, `Primary action below fold ${direction}`)
        await page.screenshot({ path: path.join(out, `${direction}-${width}.png`), fullPage: true })
        await page.getByRole('button', { name: '放大检查参考图 1', exact: true }).click()
        await page.keyboard.press('Escape')
        assert.equal(await page.evaluate(() => document.activeElement.getAttribute('data-preview')), '0')
        if (direction === 'c') { await page.getByRole('button', {name:'继续设定创意'}).click(); assert(await page.locator('#intention').isVisible()); assert(!(await page.locator('.asset-area').isVisible())) }
        const recipe = page.getByRole('button', { name: '查看配方' })
        await recipe.click()
        assert(await page.locator('#recipe-dialog').evaluate(el => el.open))
        await page.keyboard.press('Escape')
        assert.equal(await page.evaluate(() => document.activeElement.id), 'recipe')
        if (direction === 'c') await page.locator('[data-step=assets]').click()
        await page.getByRole('button', { name: '向后移动参考图 1', exact: true }).click()
        assert((await page.locator('.asset-image img').first().getAttribute('src')).includes('look-02'))
        if (direction === 'c') await page.locator('[data-step=confirm]').click()
        await page.locator('#increase').click()
        assert.equal(await page.locator('#quantity').innerText(), '2')
        await page.locator('#acknowledge').check()
        assert(await page.locator('#submit').isEnabled())
        if (width === 1440) await page.screenshot({ path: path.join(out, `${direction}-configured.png`), fullPage: true })
        await page.locator('#submit').click()
        assert(await page.locator('#result-panel').isVisible())
        assert.equal(await page.locator('#result-content h3').innerText(), '正在生成 · 样稿状态')
        await page.getByRole('button', { name: '失败', exact: true }).click()
        assert(await page.getByRole('alert').filter({ hasText: '示例任务生成失败' }).isVisible())
        await page.getByRole('button', { name: '安全查询', exact: true }).click()
        await page.getByRole('button', { name: '空结果', exact: true }).click()
        assert(await page.getByRole('heading', { name: '暂无生成结果' }).isVisible())
        await page.getByRole('button', { name: '待审核', exact: true }).click()
        await page.screenshot({ path: path.join(out, `${direction}-${width}-review.png`), fullPage: true })
        await page.getByRole('button', { name: '查看审核面板', exact: true }).click()
        await page.locator('#review-decision').selectOption('rejected')
        await page.locator('#review-save').click()
        assert.equal(await page.locator('#review-error').innerText(), '请填写拒绝原因。')
        await page.locator('#review-reason').fill('样稿检查')
        await page.locator('#review-save').click()
        assert.equal(await page.locator('#review-dialog').evaluate(el => el.open), false)
        await page.getByRole('tab', { name: '准备素材' }).click()
        const imageBytes = await fs.readFile(path.join(root, 'media/look-01.jpg'))
        if (direction === 'c') await page.locator('[data-step=assets]').click()
        await page.locator('#file-picker').setInputFiles(Array.from({ length: 5 }, (_, index) => ({
          name: `sample-${index}.jpg`, mimeType: 'image/jpeg',
          buffer: imageBytes,
        })))
        assert.equal(await page.locator('.asset').count(), 7)
        await page.waitForFunction(() => [...document.querySelectorAll('.asset-image img')].every(image => image.complete && image.naturalWidth > 0))
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
        await page.screenshot({ path: path.join(out, `${direction}-${width}-seven.png`), fullPage: true })
        await page.locator('#file-picker').setInputFiles({
          name: 'extra.jpg', mimeType: 'image/jpeg', buffer: await fs.readFile(path.join(root, 'media/look-01.jpg')),
        })
        assert.equal(await page.locator('.asset').count(), 7)
        await page.getByRole('button', { name: '删除参考图 1', exact: true }).click()
        assert.equal(await page.locator('.asset').count(), 6)
        if (width === 390) {
          if (direction === 'c') await page.locator('[data-step=confirm]').click()
          await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
          const safe = await page.evaluate(() => ({
            actionBottom: document.querySelector('#submit').getBoundingClientRect().bottom,
            navigationTop: document.querySelector('.mobile-nav').getBoundingClientRect().top,
          }))
          assert(safe.actionBottom <= safe.navigationTop, 'Bottom navigation obscures submit action')
        }
        report.cases.push({ direction, width, height, geometry, checks: ['images', 'overflow', 'labels', 'focus-restore', 'recipe', 'sort', 'quantity', 'submit-gate', 'local-submit', 'states', 'review-validation', 'seven-image-limit', 'remove'] })
        await context.close()
      }
    }
    assert.deepEqual(report.errors, [])
    assert.deepEqual(report.externalRequests, [])
    report.passed = true
  } finally {
    await fs.writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2))
    await browser.close()
  }
  console.log(JSON.stringify({ passed: report.passed, cases: report.cases.length, browser: report.browser, out }))
}
main().catch(error => { console.error(error); process.exitCode = 1 })
