import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
const requireFrontend = createRequire(resolve(root, 'frontend/package.json'))
const { createServer } = await import(pathToFileURL(requireFrontend.resolve('vite')).href)
const playwrightPath = process.env.PLAYWRIGHT_MODULE
if (!playwrightPath) throw new Error('Set PLAYWRIGHT_MODULE to the installed playwright entry file')
const { chromium } = createRequire(import.meta.url)(playwrightPath)
const reportDir = process.env.UI_REVIEW_REPORT_DIR
if (!reportDir) throw new Error('Set UI_REVIEW_REPORT_DIR to an external evidence directory')
await mkdir(reportDir, { recursive: true })

// This fixture mounts the real page but never authenticates or uses live APIs.
const html = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import React from 'react';
import {createRoot} from 'react-dom/client';
import {ImageCenter} from '/src/ImageCenter.tsx';
import {createImageCenterDraft} from '/src/imageCenterModel.ts';
import {saveImageCenterDraft} from '/src/imageCenterStore.ts';
import '/src/styles.css';
const canvas = document.createElement('canvas'); canvas.width=240; canvas.height=320;
const ctx=canvas.getContext('2d'); ctx.fillStyle='#e5edf0'; ctx.fillRect(0,0,240,320); ctx.fillStyle='#16805e'; ctx.fillRect(65,60,110,220);
const blob = await new Promise(resolve=>canvas.toBlob(resolve));
const file = new File([blob], 'synthetic-product.png', {type:'image/png'});
const draft=createImageCenterDraft('fixture-draft','fixture-outfit'); draft.activeTab='results';
draft.tasks=[{id:'fixture-task',outfitId:'fixture-outfit',outfitName:'合成测试服装',sku:'TEST',provider:'gpt',modes:['fusion'],resultCount:2,aspectRatio:'3:4',resolution:'1k',quality:'medium',outputFormat:'png',allowBackInference:false,storyboardShots:[],status:'completed',batchId:null,providerTaskId:null,providerTaskIds:[],modelId:'fixture',createdAt:new Date().toISOString(),prompt:{fusion:'',storyboard:''},model:{front:file,back:null,side:null},product:{front:file,back:null,side:null},outputs:[1,2].map(n=>({id:'output-'+n,kind:'fusion',view:'front',label:'合成结果 '+n,file,url:'',qualificationStatus:'PENDING'})),error:'',errorCode:null,retryable:null}];
await saveImageCenterDraft(draft);
createRoot(document.getElementById('root')).render(React.createElement(ImageCenter,{active:true,openTaskId:null,onPrepareVideos:()=>{},onNotifications:()=>{},onActiveTasksChange:()=>{}}));
</script></body></html>`
const server = await createServer({ root: resolve(root, 'frontend'), server: { host: '127.0.0.1', port: 0, strictPort: false }, logLevel: 'error', plugins: [{name:'review-fixture',configureServer(vite) {
  vite.middlewares.use('/__review_fixture', async (_req, res, next) => {
    try { res.setHeader('Content-Type','text/html'); res.end(await vite.transformIndexHtml('/__review_fixture', html)) }
    catch (error) { next(error) }
  })
}}] })
let browser
try {
  await server.listen()
  const port = server.httpServer.address().port
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage()
  const writes = []
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', async route => {
    if (route.request().url().includes('/quality-decision')) {
      writes.push(route.request().postDataJSON())
      const id = route.request().url().split('/').at(-2)
      await route.fulfill({json:{id,qualificationStatus:writes.at(-1).decision,qualityGates:{},reviewedAt:new Date().toISOString(),humanReviewSeconds:1}})
    } else await route.fulfill({status:404,json:{detail:'Fixture blocks all live APIs'}})
  })
  await page.goto(`http://127.0.0.1:${port}/__review_fixture`)
  await page.getByRole('heading',{name:'图片中心',exact:true}).waitFor()
  await page.getByRole('button',{name:'勾选合成结果 1',exact:true}).click()
  assert.equal(writes.length,0,'Selection must not write an approval')
  assert.equal(await page.locator('.image-output-card__quality').first().innerText(),'待人工审核')
  for (const width of [1440,1024,768,390]) {
    await page.setViewportSize({width,height:900})
    await page.screenshot({path:resolve(reportDir,`image-review-${width}.png`),fullPage:true})
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Overflow at ${width}`)
  }
  await page.getByRole('button',{name:'审核合成结果 1',exact:true}).click()
  await page.getByRole('radio',{name:'退回',exact:true}).check()
  assert(await page.getByRole('button',{name:'保存审核',exact:true}).isDisabled())
  await page.getByLabel('退回原因（必填）').fill('合成测试：商品颜色不一致')
  await page.screenshot({path:resolve(reportDir,'review-drawer-390.png'),fullPage:true})
  await page.getByRole('button',{name:'保存审核',exact:true}).click()
  await page.getByText('已拒绝',{exact:true}).waitFor()
  assert.equal(writes.length,1)
  assert.equal(writes[0].decision,'REJECTED')
  assert.equal(writes[0].notes,'合成测试：商品颜色不一致')
  await page.getByRole('button',{name:'审核合成结果 2',exact:true}).click()
  await page.keyboard.press('Escape')
  assert(await page.getByRole('button',{name:'审核合成结果 2',exact:true}).evaluate(el=>el===document.activeElement))
  assert.deepEqual(errors,[])
  await writeFile(resolve(reportDir,'result.json'),JSON.stringify({selectionWrites:0,explicitReviewWrites:writes.length,rejectionReason:true,escapeFocusRestored:true,viewports:[1440,1024,768,390],pageErrors:errors},null,2))
  console.log('Selection isolation and four viewport checks passed')
} finally {
  await browser?.close()
  await server.close()
}
