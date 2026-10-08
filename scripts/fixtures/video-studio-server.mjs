import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createPageResponses } from './ui-page-responses.mjs'

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)))

// This isolated server has no proxy, environment loading, provider SDK, or real database.
export async function createStudioFixtureServer({ cacheDir, port = 0, media = null, autoProgress = false }) {
  assert(cacheDir, 'An external Vite cache directory is required')
  const frontendRequire = createRequire(resolve(root, 'frontend/package.json'))
  const { createServer } = await import(pathToFileURL(frontendRequire.resolve('vite')).href)
  const responses = createPageResponses()
  const status = responses.get('/api/v1/system/status')
  Object.assign(status.videoGeneration, { available: true, authenticated: true, enabled: true, status: 'OFFLINE_FIXTURE', model: 'offline-fixture' })
  const template = responses.get('/api/v1/video-templates')[0]
  template.name = '服装多镜头展示'
  template.description = '商品轮廓与细节的有序展示'
  template.actionPresets = { turn: { label: '服装展示', instruction: '缓慢侧身，结束时停稳并保持商品可见' } }
  template.cameraPresets = { fixed: { label: '固定镜头', instruction: '保持完整服装轮廓可见' } }
  responses.get('/api/v1/video-templates').push({
    ...structuredClone(template), id: 'second-template', name: '细节展示', minImages: 2,
  })
  responses.set('/api/v1/admin/kling/elements', {
    items: [{ id: 'fixture-character', name: '人物参考', description: '离线合成参考',
      status: 'succeed', imageUrls: ['/api/v1/fixture-media/product.png'], raw: {} }],
    pageNum: 1, pageSize: 100, total: 1, official: false,
  })
  const baseTask = structuredClone(responses.get('/api/v1/tasks')[1])
  responses.set('/api/v1/tasks', [])
  const state = { mode: 'success', phase: 'QUEUED', writes: [], reads: [], unexpected: [], tasks: [], uploads: 0, media, video: null, failAt: null }
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>衣影工坊 · 离线预览</title></head><body><div style="padding:8px 16px;background:#e5f6ef;color:#145c46;font:13px system-ui" role="note">离线预览 · 生成仅模拟，不调用真实 Provider</div><div id="root"></div><script type="module">
import React from 'react'; import {createRoot} from 'react-dom/client';
import App from '/src/app/App.tsx'; import '/src/styles.css';
createRoot(document.getElementById('root')).render(React.createElement(App));
</script></body></html>`
  function updateTask(task) {
    const next = structuredClone(task)
    const elapsed = (Date.now() - Date.parse(task.createdAt)) / 1000
    const phase = autoProgress
      ? elapsed < 4 ? 'QUEUED' : elapsed < 8 ? 'PREPARING' : elapsed < 12 ? 'GENERATING' : elapsed < 16 ? 'VALIDATING' : 'AWAITING_FINAL_APPROVAL'
      : state.phase
    next.phase = phase
    next.variants[0].generationStatus = phase === 'DELIVERABLE' || phase === 'AWAITING_FINAL_APPROVAL' ? 'SUCCEEDED' : phase === 'ACTION_REQUIRED' ? 'FAILED' : phase === 'QUEUED' ? 'PENDING' : 'RUNNING'
    if (['DELIVERABLE', 'AWAITING_FINAL_APPROVAL'].includes(phase)) {
      next.variants[0].downloadArtifactId = 'fixture-artifact'
      next.variants[0].validationStatus = 'PASSED'
      next.variants[0].downloadStatus = 'SUCCEEDED'
    }
    if (phase === 'DELIVERABLE') next.variants[0].finalApprovalStatus = 'APPROVED'
    next.updatedAt = new Date().toISOString()
    return next
  }
  const server = await createServer({
    configFile: false, envFile: false, root: resolve(root, 'frontend'), cacheDir, logLevel: 'error',
    server: { host: '127.0.0.1', port, strictPort: false },
    plugins: [{ name: 'video-studio-offline', configureServer(vite) {
      vite.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url, 'http://127.0.0.1')
        if (url.pathname === '/' || url.pathname === '/studio/video') {
          res.setHeader('Content-Type', 'text/html')
          res.setHeader('Set-Cookie', 'synthetic_csrf=fixture-csrf; Path=/; SameSite=Strict')
          return res.end(await vite.transformIndexHtml(url.pathname, html))
        }
        if (!url.pathname.startsWith('/api/')) return next()
        const send = (value, code = 200) => { res.statusCode = code; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(value)) }
        if (req.method === 'GET') {
          state.reads.push(url.pathname)
          if (url.pathname === '/api/v1/fixture-media/product.png') {
            res.setHeader('Content-Type', 'image/png')
            return res.end(state.media)
          }
          if (url.pathname === '/api/v1/downloads/fixture-artifact' && state.video) {
            res.setHeader('Content-Type', 'video/webm')
            return res.end(state.video)
          }
          if (url.pathname === '/api/v1/tasks') return send(state.tasks.map(updateTask))
          if (url.pathname === '/api/v1/video-templates' && state.mode === 'no-template') return send([])
          if (url.pathname === '/api/v1/video-templates' && state.mode === 'catalog-failure') return send({ detail: '离线合成：模板读取失败' }, 503)
          const task = state.tasks.find((item) => url.pathname === `/api/v1/tasks/${item.id}`)
          if (task) return send(updateTask(task))
          if (responses.has(url.pathname)) return send(responses.get(url.pathname))
        }
        let body = ''
        for await (const part of req) body += part
        if (req.method === 'POST' && url.pathname === '/api/v1/uploads') {
          state.uploads += 1
          state.writes.push({ path: url.pathname, headers: req.headers })
          return send({ id: `fixture-upload-${state.uploads}`, originalFilename: 'fixture.png', sha256: 'fixture', width: 240, height: 320, sizeBytes: body.length, thumbnailUrl: '/api/v1/fixture-media/product.png' }, 201)
        }
        if (req.method === 'POST' && url.pathname === '/api/v1/video-tasks') {
          const payload = JSON.parse(body)
          state.writes.push({ path: url.pathname, payload, key: req.headers['idempotency-key'] })
          if (state.mode === 'unknown') return send({ detail: { code: 'WRITE_UNCERTAIN', message: '离线合成：提交结果未知' } }, 503)
          if (state.mode === 'rejected' || state.writes.filter((write) => write.path === url.pathname).length === state.failAt) return send({ detail: { code: 'INVALID_INPUT', message: '离线合成：素材未通过校验' } }, 400)
          const task = structuredClone(baseTask)
          task.id = `fixture-video-${state.tasks.length + 1}`
          task.clientTaskId = payload.clientTaskId
          task.title = '离线服装视频'
          task.settings = { durationSeconds: payload.durationSeconds }
          task.templateId = payload.templateId
          task.variants[0].id = `${task.id}-variant`
          task.phase = state.phase
          task.createdAt = new Date().toISOString()
          state.tasks.push(task)
          return send(updateTask(task), 201)
        }
        if (req.method === 'POST' && url.pathname === '/api/v1/submission-recovery/query') {
          state.writes.push({ path: url.pathname, payload: JSON.parse(body) })
          return send({ state: 'unknown', source: 'offline-fixture', checkedAt: new Date().toISOString(), auditId: 'fixture-audit', resourceId: null, resourceStatus: null, stateVersion: null, retryAllowed: false })
        }
        state.unexpected.push({ path: url.pathname, method: req.method })
        return send({ detail: 'Offline fixture has no route and never proxies requests' }, 404)
      })
    } }],
  })
  await server.listen()
  return { server, state, responses, origin: server.resolvedUrls.local[0].replace(/\/$/, '') }
}
