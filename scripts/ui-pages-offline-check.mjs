import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createPageResponses } from './fixtures/ui-page-responses.mjs'
import { createAdminResponses } from './fixtures/ui-admin-responses.mjs'
import { collectPageSnapshot, isPageReady, ROUTES as smokeRoutes } from './ui-smoke.mjs'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
const requireFrontend = createRequire(resolve(root, 'frontend/package.json'))
const { createServer } = await import(pathToFileURL(requireFrontend.resolve('vite')).href)
assert(process.env.PLAYWRIGHT_MODULE, 'Set PLAYWRIGHT_MODULE to an installed playwright entry')
assert(process.env.UI_PAGES_REPORT_DIR, 'Set UI_PAGES_REPORT_DIR to an external evidence directory')
const reportDir = resolve(process.env.UI_PAGES_REPORT_DIR)
const reportRelative = relative(root, reportDir)
assert(reportRelative.startsWith('..') || isAbsolute(reportRelative), 'Evidence must stay outside this checkout')
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE)
await mkdir(reportDir, {recursive:true})

const routes = [
  {name:'make', query:'', selector:'.home-view:not([hidden])', heading:'视频工作室', reads:['video-templates','site-style-profiles'], loadingText:'正在加载配置'},
  {name:'records', query:'?view=records', selector:'.page-view > .records-overview', heading:'任务', reads:[]},
  {name:'library', query:'?view=library', selector:'.generated-assets-view', heading:'生成资产', reads:['image-generation-batches']},
  {name:'settings', query:'?view=settings', selector:'.settings-view', heading:'偏好设置', reads:['auth/preferences/video-learning','auth/preferences/prompt-confirmation'], loadingText:'正在读取个人成片偏好'},
  {name:'admin-overview', query:'?view=admin', selector:'.admin-view', heading:'管理中心', section:'运行总览', reads:['admin/operations'], loadingText:'正在加载运行状态'},
  {name:'admin-accounts', query:'?view=admin&section=accounts', selector:'.admin-view', heading:'管理中心', section:'成员账号', reads:['admin/users'], loadingText:'正在读取成员账号…'},
  {name:'admin-providers', query:'?view=admin&section=providers', selector:'.admin-view', heading:'管理中心', section:'生成提供商', reads:['admin/kling/config','admin/kling/status','admin/wavespeed/config','admin/bach/config'], loadingText:'正在读取可灵配置…'},
  {name:'admin-security', query:'?view=admin&section=security', selector:'.admin-view', heading:'管理中心', section:'流程与分析', reads:['admin/operations','admin/credentials'], loadingText:'正在读取'},
]
const widths = [1440,1024,768,390]
const selectedRoutes = process.env.UI_PAGES_ROUTE
  ? routes.filter(route => route.name === process.env.UI_PAGES_ROUTE)
  : routes
assert(selectedRoutes.length > 0,'Unknown UI_PAGES_ROUTE')
const html = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import React from 'react';
import {createRoot} from 'react-dom/client';
import App from '/src/app/App.tsx';
import '/src/styles.css';
createRoot(document.getElementById('root')).render(React.createElement(App));
</script></body></html>`
const server = await createServer({
  configFile:false, envFile:false, root:resolve(root,'frontend'),
  cacheDir:resolve(reportDir,'vite-cache'), logLevel:'error',
  server:{host:'127.0.0.1',port:0,strictPort:false},
  plugins:[{name:'offline-pages',configureServer(vite) {
    vite.middlewares.use('/__pages_fixture',async (_req,res,next) => {
      try {res.setHeader('Content-Type','text/html'); res.end(await vite.transformIndexHtml('/__pages_fixture',html))}
      catch (error) {next(error)}
    })
  }}],
})
const report = {
  scope:'isolated-app-pages-not-full-U08', sourceHead:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  capturedAt:new Date().toISOString(), browserVersion:null, fixtureRecords:3,
  widths, cases:[], safety:{externalRequests:[],writeRequests:[],unmatchedApiRequests:[]},
  selectedRoutes:selectedRoutes.map(route => route.name),
  exclusions:['paid submission','live authorization','all keyboard workflows','contrast','200% zoom','performance','resource lifecycle'],
}
report.sourceHashes = Object.fromEntries(await Promise.all([
  'scripts/ui-pages-offline-check.mjs','scripts/fixtures/ui-page-responses.mjs',
  'scripts/fixtures/ui-admin-responses.mjs','scripts/ui-smoke.mjs',
  'frontend/src/styles.css','frontend/src/app/App.tsx',
].map(async path => [path,createHash('sha256').update(await readFile(resolve(root,path))).digest('hex')])))
let browser

async function runCase(route, width, state = 'populated', role = 'ADMIN') {
  const name = `${route.name}-${state}-${role.toLowerCase()}-${width}`
  const context = await browser.newContext({viewport:{width,height:900},serviceWorkers:'block', reducedMotion:'reduce'})
  const page = await context.newPage()
  page.setDefaultTimeout(12000)
  const errors = []
  const pending = new Set()
  const featureRequests = new Set()
  page.on('pageerror',error => errors.push(error.message))
  const responses = new Map([...createPageResponses({role,empty:state === 'empty'}),...createAdminResponses()])
  if (route.name === 'library' && state === 'populated') {
    const output = {id:'fixture-image', kind:'fusion', view:'front', label:'验收合格图片', url:'/api/v1/fixture-media/product.png', downloadUrl:'/api/v1/fixture-media/product.png', artifactId:'fixture-image-artifact', qualificationStatus:'QUALIFIED', synthetic:false}
    responses.set('/api/v1/image-generation-batches', [{id:'fixture-batch', name:'验收图片批次', status:'completed', items:[{id:'fixture-item', outfitId:'fixture-product', status:'completed', outputs:[output, {...output, id:'pending-image', label:'未审核图片', qualificationStatus:'PENDING'}, {...output, id:'synthetic-image', label:'合成演示图片', synthetic:true}]}]}])
  }
  if (state === 'empty') responses.set('/api/v1/admin/users',[])
  const featurePaths = new Set([
    '/api/v1/video-templates','/api/v1/site-style-profiles','/api/v1/motion-actions',
    '/api/v1/image-generation-batches',
    '/api/v1/ai-usage/quota',
    '/api/v1/creative-workflow/tasks',
    '/api/v1/auth/preferences/video-learning','/api/v1/auth/preferences/prompt-confirmation',
    '/api/v1/admin/operations','/api/v1/admin/users','/api/v1/admin/credentials',
    '/api/v1/admin/kling/config','/api/v1/admin/kling/status','/api/v1/admin/wavespeed/config','/api/v1/admin/bach/config',
  ])
  const origin = server.resolvedUrls.local[0].replace(/\/$/,'')
  let releaseLoading
  let failImageHistory = false
  const loadingGate = new Promise(resolveGate => {releaseLoading = resolveGate})
  await context.route('**/*',async interception => {
    const request = interception.request()
    const url = new URL(request.url())
    if (url.origin !== origin) {
      report.safety.externalRequests.push({case:name,origin:url.origin})
      return interception.abort()
    }
    if (!url.pathname.startsWith('/api/')) return interception.continue()
    if (request.method() !== 'GET') {
      report.safety.writeRequests.push({case:name,path:url.pathname,method:request.method()})
      return interception.fulfill({status:405,json:{detail:'Offline fixture blocks every write'}})
    }
    if (failImageHistory && url.pathname === '/api/v1/image-generation-batches') {
      return interception.fulfill({status:503,json:{detail:'隔离验收：图片历史暂时不可用'}})
    }
    if (url.pathname === '/api/v1/fixture-media/product.png') {
      return interception.fulfill({contentType:'image/png',body:mediaPng})
    }
    if (!responses.has(url.pathname)) {
      report.safety.unmatchedApiRequests.push({case:name,path:url.pathname})
      return interception.fulfill({status:404,json:{detail:'No synthetic response defined'}})
    }
    pending.add(request)
    if (featurePaths.has(url.pathname)) featureRequests.add(url.pathname)
    try {
      if (state === 'loading' && featurePaths.has(url.pathname)) await loadingGate
      if (state === 'error' && featurePaths.has(url.pathname)) {
        return await interception.fulfill({status:503,json:{detail:{
          code:'SYNTHETIC_OFFLINE_FAILURE',message:'合成验收：读取失败，未访问真实服务',
        }}})
      }
      return await interception.fulfill({json:responses.get(url.pathname)})
    } finally {pending.delete(request)}
  })
  const result = {name,route:route.name,width,state,role,passed:false,pageErrors:errors}
  try {
    await page.goto(`${origin}/__pages_fixture${route.query}`, {waitUntil:'domcontentloaded',timeout:30_000})
    if (role === 'USER' && route.section) {
      await page.getByText('没有管理中心权限',{exact:true}).waitFor()
      assert.equal(await page.locator('.admin-view').count(),0)
      assert.equal([...featureRequests].filter(path => path.startsWith('/api/v1/admin/') && path !== '/api/v1/admin/kling/elements').length,0)
      result.permissionBoundary = 'UI-only denial; not server authorization'
      const deniedRoute = smokeRoutes.find(item => item.name === route.name)
      const deniedSnapshot = await page.evaluate(
        ({collector,route}) => (0,eval)(`(${collector})`)(route),
        {collector:collectPageSnapshot.toString(),route:deniedRoute},
      )
      assert(!isPageReady(deniedRoute,deniedSnapshot),'Denied route must not pass smoke')
      result.smokeRejectsDeniedPage = true
    } else {
      const heading = page.getByRole('heading',{name:route.heading,exact:true})
      await heading.waitFor()
      assert.equal(await heading.count(),1)
      const target = page.locator(route.selector)
      assert(await target.isVisible(),`Target hidden: ${route.name}`)
      if (route.section) {
        assert.equal(await page.locator('.subnav-tabs [aria-current="page"]').innerText().then(text => text.includes(route.section)),true)
      }
      if (state === 'loading') {
        await target.getByText(route.loadingText,{exact:false}).first().waitFor()
        result.loadingIndicator = route.loadingText
      } else {
        await page.waitForFunction(() => !document.querySelector('.app-boot-screen,.page-loading'))
        await assertEventually(() => route.reads.every(path => featureRequests.has(`/api/v1/${path}`)) && pending.size === 0)
        await page.waitForFunction(() => !document.querySelector('.app-boot-screen,.page-loading,.library-loading'))
        await page.waitForFunction(() => Array.from(document.querySelectorAll('input[aria-label="根据成片反馈持续学习"]')).every(el => !el.disabled || document.querySelector('[role="alert"]')))
        await page.evaluate(() => new Promise(resolveFrame => requestAnimationFrame(() => requestAnimationFrame(resolveFrame))))
        await page.waitForFunction(() => Array.from(document.images).filter(img => img.offsetWidth > 0).every(img => img.complete && img.naturalWidth > 0))
        if (state === 'error') await target.getByText('合成验收：读取失败，未访问真实服务',{exact:false}).first().waitFor()
      }
      result.visibleHeading = route.heading
      if (route.name === 'records' && state === 'populated') {
        assert.equal(await page.locator('.task-table-row').count(),2)
        assert.equal(await page.locator('.records-completed .result-card').count(),1)
      }
      if (state === 'empty') {
        if (route.name === 'records') {
          await page.getByText('还没有任务',{exact:true}).waitFor()
          assert.equal(await page.locator('.task-table-row,.records-completed .result-card').count(),0)
        }
        if (route.name === 'library') await target.getByText('还没有可查看的生成资产',{exact:true}).waitFor()
        if (route.name === 'admin-accounts') await target.getByText('还没有成员账号',{exact:true}).waitFor()
        result.emptyFixture = true
      }
      if (route.name === 'make' && state === 'populated') {
        await page.locator('.upload-panel--storyboard input[type="file"]').first().setInputFiles({
          name:'合成分镜长文件名_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.png',mimeType:'image/png',buffer:mediaPng,
        })
        const preview = page.getByRole('button',{name:'查看图片 1 大图',exact:true})
        await preview.waitFor()
        await preview.locator('img').evaluate(img => img.decode())
        await preview.focus()
        await page.keyboard.press('Enter')
        await page.getByRole('dialog').waitFor()
        await page.getByRole('dialog').locator('img').evaluate(img => img.decode())
        await page.keyboard.press('Escape')
        await page.getByRole('dialog').waitFor({state:'hidden'})
        assert(await preview.evaluate(el => el === document.activeElement),'Composer preview focus not restored')
        assert(await page.getByRole('button',{name:'开始生成',exact:false}).isDisabled())
        result.localUploadPreview = {images:1,enterOpens:true,escapeFocusRestored:true,paidSubmitDisabled:true}
        await page.evaluate(() => scrollTo(0,0))
      }
      const smokeRoute = smokeRoutes.find(item => item.name === route.name)
      result.smokeSnapshot = await page.evaluate(
        ({collector,route}) => (0,eval)(`(${collector})`)(route),
        {collector:collectPageSnapshot.toString(),route:smokeRoute},
      )
      assert(isPageReady(smokeRoute,result.smokeSnapshot),`Specific visible-route smoke assertion failed: ${JSON.stringify(result.smokeSnapshot)}`)
      if (state === 'populated' && role === 'ADMIN' && route.name === 'library') {
        await target.getByText('2 个可查看结果', {exact:true}).waitFor()
        const image = target.getByRole('button', {name:'预览验收合格图片', exact:true})
        await image.locator('img').evaluate(img => img.decode())
        assert.equal(await target.locator('.image-result-card').count(), 1, 'Only qualified, non-synthetic images are published')
        await image.click()
        const preview = page.getByRole('dialog', {name:'验收合格图片大图预览', exact:true})
        await preview.waitFor()
        await preview.locator('img').waitFor()
        await preview.locator('img').evaluate(img => img.decode())
        await page.keyboard.press('Escape')
        await preview.waitFor({state:'hidden'})
        await target.getByRole('textbox', {name:'搜索生成资产'}).fill('不存在的资产')
        await target.getByText('0 个可查看结果', {exact:true}).waitFor()
        await target.getByRole('textbox', {name:'搜索生成资产'}).fill('')
        await target.getByRole('combobox', {name:'媒体类型'}).selectOption('image')
        await target.getByText('1 个可查看结果', {exact:true}).waitFor()
        assert.equal(await target.locator('.image-result-card').count(), 1)
        await target.getByRole('combobox', {name:'媒体类型'}).selectOption('video')
        await target.getByText('1 个可查看结果', {exact:true}).waitFor()
        assert.equal(await target.locator('.image-result-card').count(), 0)
        await target.getByRole('combobox', {name:'媒体类型'}).selectOption('all')
        await target.getByText('2 个可查看结果', {exact:true}).waitFor()
        result.assetWorkflow = 'qualification filtering, image preview, search and media filtering'
        const taskButton = target.getByRole('button', {name:'查看任务详情', exact:true}).first()
        await taskButton.scrollIntoViewIfNeeded()
        await taskButton.click()
        const scrollBefore = await page.evaluate(() => JSON.parse(sessionStorage.getItem('app.records-return')).scrollY)
        await page.locator('.foundation-drawer').waitFor({state:'visible'})
        assert.equal(new URL(page.url()).searchParams.get('task'), 'synthetic-task-2')
        await page.keyboard.press('Escape')
        await page.locator('.foundation-drawer').waitFor({state:'hidden'})
        assert.equal(new URL(page.url()).searchParams.get('view'), 'library')
        await page.waitForFunction(expected => Math.abs(window.scrollY - expected) < 4, scrollBefore)
        result.taskReturn = 'task detail returns to generated assets and restores scroll'
        failImageHistory = true
        await page.goto(`${origin}/__pages_fixture?view=library`, {waitUntil:'domcontentloaded',timeout:30_000})
        const historyError = page.getByRole('alert').filter({hasText:'图片历史读取失败'})
        await historyError.waitFor()
        await page.locator('.generated-assets-view').getByText('1 个可查看结果', {exact:true}).waitFor()
        assert.equal(await page.locator('.generated-assets-view .image-result-card').count(),0)
        failImageHistory = false
        await historyError.getByRole('button', {name:'重试',exact:true}).click()
        await historyError.waitFor({state:'hidden'})
        await page.locator('.generated-assets-view').getByText('2 个可查看结果', {exact:true}).waitFor()
        result.historyRecovery = 'image failure does not hide video history; explicit retry restores images'
      }
    }
    if (state !== 'loading') await page.waitForFunction(() => !document.querySelector('.app-boot-screen,.page-loading'))
    await page.evaluate(() => { document.activeElement?.blur(); scrollTo(0,0) })
    await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))))
    result.documentWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    result.horizontalOverflow = result.documentWidth > width + 1
    await page.screenshot({path:resolve(reportDir,`${name}.png`),fullPage:true})
    if (route.name === 'records' && state === 'populated' && role === 'ADMIN') {
      result.rowGeometry = await page.locator('.task-table-row').evaluateAll(rows => rows.map(row => {
        const title = row.querySelector('.task-name-cell strong')
        const status = row.children[1]
        const reason = status.querySelector('small')
        const rowRect = row.getBoundingClientRect()
        const statusRect = status.getBoundingClientRect()
        return {titleWidth:title.clientWidth,reasonWidth:reason?.clientWidth ?? 0,
          reasonScrollWidth:reason?.scrollWidth ?? 0,
          statusInsideRow:statusRect.left >= rowRect.left && statusRect.right <= rowRect.right + 1}
      }))
      assert(result.rowGeometry.every(row => row.titleWidth >= 120 && row.statusInsideRow &&
        row.reasonScrollWidth <= row.reasonWidth + 1),'Task title squeezed or long error code clipped inside row')
    }
    if (state === 'populated' && role === 'ADMIN' && route.name === 'records') {
      const search = page.getByRole('textbox',{name:'搜索任务名称',exact:true})
      await search.fill('合成验收1')
      await page.waitForFunction(() => document.querySelectorAll('.task-table-row').length === 1)
      assert(new URL(page.url()).searchParams.get('q') === '合成验收1')
      await search.fill('不存在的合成关键词')
      await page.getByText('没有匹配“ 不存在的合成关键词 ”的任务'.replaceAll(' ',''),{exact:true}).waitFor()
      await page.getByRole('button',{name:'清除搜索关键词',exact:true}).click()
      await page.waitForFunction(() => document.querySelectorAll('.task-table-row').length === 2)
      result.searchWorkflow = 'matching row, no-match empty state, URL query, clear'
    }
    if (state === 'populated' && role === 'ADMIN' && route.name === 'settings') {
      const general = page.getByRole('tab',{name:'通用内容',exact:false})
      await general.focus()
      await page.keyboard.press('ArrowRight')
      const brand = page.getByRole('tab',{name:'品牌专属',exact:false})
      await page.waitForFunction(() => document.activeElement?.id === 'brand-tab' &&
        document.activeElement.getAttribute('aria-selected') === 'true')
      assert(await brand.evaluate(el => el === document.activeElement && el.getAttribute('aria-selected') === 'true'))
      await page.keyboard.press('Home')
      await page.waitForFunction(() => document.activeElement?.id === 'general-tab' &&
        document.activeElement.getAttribute('aria-selected') === 'true')
      assert(await general.evaluate(el => el === document.activeElement && el.getAttribute('aria-selected') === 'true'))
      await page.getByRole('textbox',{name:'搜索动作库',exact:true}).fill('不存在的合成关键词')
      await page.getByText('没有匹配内容',{exact:true}).waitFor()
      await page.getByRole('button',{name:'清除筛选',exact:true}).first().click()
      await page.getByRole('heading',{name:'合成正面服装展示与细节检查动作',exact:true}).waitFor()
      result.libraryWorkflow = 'brand asset library remains available inside settings'
    }
    assert(!result.horizontalOverflow,`Horizontal overflow: ${result.documentWidth} > ${width}`)
    assert.deepEqual(errors,[])
    result.passed = true
  } catch (error) {
    result.failure = error.message
    await page.screenshot({path:resolve(reportDir,`${name}-failure.png`),fullPage:true}).catch(() => {})
  } finally {
    releaseLoading()
    await context.close()
    report.cases.push(result)
    console.log(`${result.passed ? 'PASS' : 'FAIL'} ${name}${result.failure ? `: ${result.failure}` : ''}`)
  }
}

async function assertEventually(predicate) {
  const until = Date.now() + 12000
  while (!predicate()) {
    assert(Date.now() < until,'Synthetic API reads did not settle')
    await new Promise(resolveWait => setTimeout(resolveWait,25))
  }
}

let mediaPng
try {
  await server.listen()
  browser = await chromium.launch({channel: process.env.UI_BROWSER_CHANNEL || 'msedge', headless:true})
  report.browserVersion = browser.version()
  const mediaPage = await browser.newPage()
  const base64 = await mediaPage.evaluate(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 240; canvas.height = 320
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#edf2f4'; ctx.fillRect(0,0,240,320)
    ctx.fillStyle = '#16805e'; ctx.fillRect(65,60,110,220)
    return canvas.toDataURL('image/png').split(',')[1]
  })
  mediaPng = Buffer.from(base64,'base64')
  await mediaPage.close()
  for (const route of selectedRoutes) for (const width of widths) await runCase(route,width)
  for (const route of selectedRoutes.filter(route => ['make','records','library','admin-accounts'].includes(route.name))) {
    for (const width of widths) await runCase(route,width,'empty')
  }
  for (const state of ['error','loading']) {
    for (const route of selectedRoutes.filter(route => route.name !== 'records' && route.name !== 'library')) await runCase(route,390,state)
  }
  for (const route of selectedRoutes.filter(route => route.section)) await runCase(route,390,'populated','USER')
  report.passed = report.cases.every(test => test.passed) && Object.values(report.safety).every(list => list.length === 0)
  await writeFile(resolve(reportDir,'result.json'),JSON.stringify(report,null,2))
  assert(report.passed,'Offline page acceptance has failures; inspect external result.json')
} finally {
  await browser?.close()
  await server.close()
}
