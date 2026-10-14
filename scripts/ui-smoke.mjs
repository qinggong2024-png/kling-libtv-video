import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const PROJECT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

export const ROUTES = [
  { name: 'images', query: '?view=images', selector: '.image-center.page-view', heading: '\u56fe\u7247\u5de5\u4f5c\u5ba4' },
  { name: 'make', query: '', selector: '.home-view', heading: '\u89c6\u9891\u5de5\u4f5c\u5ba4' },
  { name: 'records', query: '?view=records', selector: '.page-view > .records-overview', heading: '\u4efb\u52a1' },
  { name: 'library', query: '?view=library', selector: '.generated-assets-view', heading: '\u751f\u6210\u8d44\u4ea7' },
  { name: 'admin-overview', query: '?view=admin', selector: '.admin-view .admin-section-content > .admin-summary-grid', heading: '\u7ba1\u7406\u4e2d\u5fc3', sectionLabel: '\u8fd0\u884c\u603b\u89c8', requiresAdmin: true },
  { name: 'admin-accounts', query: '?view=admin&section=accounts', selector: '.admin-view .admin-section-content > .account-management-section', heading: '\u7ba1\u7406\u4e2d\u5fc3', sectionLabel: '\u6210\u5458\u8d26\u53f7', requiresAdmin: true },
  { name: 'admin-providers', query: '?view=admin&section=providers', selector: '.admin-view .admin-section-content > .provider-section', heading: '\u7ba1\u7406\u4e2d\u5fc3', sectionLabel: '\u751f\u6210\u63d0\u4f9b\u5546', requiresAdmin: true },
  { name: 'admin-security', query: '?view=admin&section=security', selector: '.admin-view .admin-section-content > .prompt-confirmation-section', heading: '\u7ba1\u7406\u4e2d\u5fc3', sectionLabel: '\u6d41\u7a0b\u4e0e\u5206\u6790', requiresAdmin: true },
  { name: 'settings', query: '?view=settings', selector: '.settings-view', heading: '\u504f\u597d\u8bbe\u7f6e' },
]

export function isPageReady(route, snapshot) {
  return Boolean(
    snapshot
    && snapshot.readyState === 'complete'
    && snapshot.rootChildren > 0
    && snapshot.bodyTextLength > 20
    && snapshot.targetFound
    && snapshot.targetVisible
    && snapshot.pageHeading === route.heading
    && !snapshot.loginRequired
    && !snapshot.permissionDenied
    && (!route.requiresAdmin || (
      snapshot.adminRole === '\u7ba1\u7406\u5458\u6743\u9650'
      && snapshot.activeSection === route.sectionLabel
    )),
  )
}

// Self-contained so CDP can run exactly the same collector tested with DOM fixtures.
export function collectPageSnapshot(route) {
  const visible = (element) => {
    if (!element) return false
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node)
      if (node.hidden || node.getAttribute('aria-hidden') === 'true'
        || style.display === 'none' || style.visibility === 'hidden'
        || style.visibility === 'collapse' || style.contentVisibility === 'hidden'
        || Number(style.opacity) === 0) return false
    }
    return Array.from(element.getClientRects()).some((rect) => rect.width > 0 && rect.height > 0)
  }
  const candidates = Array.from(document.querySelectorAll(route.selector))
  const target = candidates.find(visible)
  const page = target?.closest('.page-view, .home-view')
  const visibleText = (selector) => {
    const element = Array.from(page?.querySelectorAll(selector) ?? []).find(visible)
    return element?.textContent.trim() ?? ''
  }
  const denialTitles = ['\u6ca1\u6709\u7ba1\u7406\u4e2d\u5fc3\u6743\u9650', '\u9700\u8981\u7ba1\u7406\u5458\u6743\u9650', '\u51ed\u636e\u7531\u7ba1\u7406\u5458\u7ef4\u62a4']
  return {
    readyState: document.readyState,
    rootChildren: document.getElementById('root')?.childElementCount ?? 0,
    bodyTextLength: document.body?.innerText.trim().length ?? 0,
    targetFound: candidates.length > 0,
    targetVisible: Boolean(target),
    pageHeading: visibleText('h1'),
    activeSection: visibleText('.subnav-tabs button[aria-current="page"] strong'),
    adminRole: visibleText('.system-health small'),
    permissionDenied: Boolean(route.requiresAdmin && Array.from(document.querySelectorAll('.page-view .empty-state > strong'))
      .some((element) => visible(element) && denialTitles.includes(element.textContent.trim()))),
    loginRequired: Array.from(document.querySelectorAll('.login-view')).some(visible),
    title: document.title,
  }
}

function parseArguments(argv) {
  const options = {
    baseUrl: process.env.UI_SMOKE_BASE_URL || 'http://127.0.0.1:5173/',
    username: process.env.UI_SMOKE_USERNAME || '',
    password: process.env.UI_SMOKE_PASSWORD || '',
    timeoutMs: Number(process.env.UI_SMOKE_TIMEOUT_MS || 15000),
    report: process.env.UI_SMOKE_REPORT || resolve(PROJECT_ROOT, 'var/reports/ui-smoke.json'),
    chrome: process.env.UI_SMOKE_CHROME || '',
  }
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index]
    if (key === '--help') options.help = true
    else if (key === '--base-url') options.baseUrl = argv[++index]
    else if (key === '--username') options.username = argv[++index]
    else if (key === '--timeout-ms') options.timeoutMs = Number(argv[++index])
    else if (key === '--report') options.report = resolve(argv[++index])
    else if (key === '--chrome') options.chrome = argv[++index]
    else throw new Error(`Unknown argument: ${key}`)
  }
  if (!Number.isFinite(options.timeoutMs) || options.timeoutMs < 1000) throw new Error('--timeout-ms must be at least 1000')
  options.baseUrl = new URL(options.baseUrl).toString()
  return options
}

function chromePath(explicitPath) {
  const candidates = [
    explicitPath,
    process.platform === 'win32' ? `${process.env.PROGRAMFILES || ''}\\Google\\Chrome\\Application\\chrome.exe` : '',
    process.platform === 'win32' ? `${process.env['PROGRAMFILES(X86)'] || ''}\\Google\\Chrome\\Application\\chrome.exe` : '',
    process.platform === 'win32' ? `${process.env.LOCALAPPDATA || ''}\\Google\\Chrome\\Application\\chrome.exe` : '',
    process.platform === 'win32' ? `${process.env.PROGRAMFILES || ''}\\Microsoft\\Edge\\Application\\msedge.exe` : '',
    process.platform === 'win32' ? `${process.env['PROGRAMFILES(X86)'] || ''}\\Microsoft\\Edge\\Application\\msedge.exe` : '',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ].filter(Boolean)
  const found = candidates.find(existsSync)
  if (!found) throw new Error('Chrome/Edge not found; set UI_SMOKE_CHROME or pass --chrome')
  return found
}

function waitForDebuggerUrl(process, timeoutMs) {
  return new Promise((resolvePromise, reject) => {
    let output = ''
    const timer = setTimeout(() => reject(new Error('Timed out waiting for Chrome DevTools endpoint')), timeoutMs)
    const consume = (chunk) => {
      output += chunk.toString()
      const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/)
      if (!match) return
      clearTimeout(timer)
      resolvePromise(match[1])
    }
    process.stderr.on('data', consume)
    process.stdout.on('data', consume)
    process.once('exit', (code) => {
      clearTimeout(timer)
      reject(new Error(`Chrome exited before DevTools was ready (exit ${code})`))
    })
  })
}

function connectCdp(url) {
  return new Promise((resolvePromise, reject) => {
    const socket = new WebSocket(url)
    let sequence = 0
    const pending = new Map()
    const listeners = new Set()
    socket.addEventListener('open', () => {
      resolvePromise({
        send(method, params = {}, sessionId) {
          const id = ++sequence
          socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }))
          return new Promise((resolveCall, rejectCall) => pending.set(id, { resolve: resolveCall, reject: rejectCall }))
        },
        onEvent(listener) { listeners.add(listener); return () => listeners.delete(listener) },
        close() { socket.close() },
      })
    })
    socket.addEventListener('error', () => reject(new Error('Chrome DevTools WebSocket connection failed')))
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data)
      if (message.id) {
        const call = pending.get(message.id)
        if (!call) return
        pending.delete(message.id)
        if (message.error) call.reject(new Error(`${message.error.message} (${message.error.code})`))
        else call.resolve(message.result)
        return
      }
      for (const listener of listeners) listener(message)
    })
  })
}

const sleep = (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds))

async function evaluate(cdp, sessionId, expression, awaitPromise = false) {
  const result = await cdp.send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true }, sessionId)
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'Runtime evaluation failed')
  return result.result.value
}

async function readPageSnapshot(cdp, sessionId, route) {
  return evaluate(cdp, sessionId, `(${collectPageSnapshot.toString()})(${JSON.stringify(route)})`)
}

async function waitForPage(cdp, sessionId, route, timeoutMs) {
  const started = Date.now()
  let snapshot = null
  while (Date.now() - started < timeoutMs) {
    snapshot = await readPageSnapshot(cdp, sessionId, route)
    if (snapshot.loginRequired || isPageReady(route, snapshot)) return snapshot
    await sleep(200)
  }
  return snapshot
}

async function loginIfRequired(cdp, sessionId, options, snapshot) {
  if (!snapshot?.loginRequired) return false
  if (!options.username || !options.password) {
    throw new Error('Authentication required; set UI_SMOKE_USERNAME and UI_SMOKE_PASSWORD')
  }
  const response = await evaluate(cdp, sessionId, `(async () => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: ${JSON.stringify(options.username)}, password: ${JSON.stringify(options.password)} }),
    })
    return { ok: response.ok, status: response.status }
  })()`, true)
  if (!response.ok) throw new Error(`Smoke-test login failed with HTTP ${response.status}`)
  return true
}

async function run() {
  const options = parseArguments(process.argv.slice(2))
  if (options.help) {
    console.log('Usage: node scripts/ui-smoke.mjs [--base-url URL] [--username USER] [--timeout-ms MS] [--report PATH] [--chrome PATH]')
    console.log('Set UI_SMOKE_PASSWORD (and optionally UI_SMOKE_USERNAME) in the process environment for shared-authentication deployments.')
    return
  }

  const startedAt = new Date().toISOString()
  const profile = await mkdtemp(resolve(tmpdir(), 'libtv-ui-smoke-'))
  const browser = spawn(chromePath(options.chrome), [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
  ], { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
  let cdp
  const results = []
  try {
    const debuggerUrl = await waitForDebuggerUrl(browser, options.timeoutMs)
    cdp = await connectCdp(debuggerUrl)
    const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' })
    const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true })
    await Promise.all(['Page.enable', 'Runtime.enable', 'Log.enable'].map((method) => cdp.send(method, {}, sessionId)))

    let activeErrors = []
    const removeListener = cdp.onEvent((message) => {
      if (message.sessionId !== sessionId) return
      if (message.method === 'Runtime.exceptionThrown') {
        const details = message.params.exceptionDetails
        activeErrors.push(`Uncaught exception: ${details.exception?.description || details.text}`)
      }
      if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
        const text = message.params.args.map((item) => item.value ?? item.description ?? '').join(' ')
        activeErrors.push(`console.error: ${text}`)
      }
      if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error' && message.params.entry.source !== 'network') {
        activeErrors.push(`browser log: ${message.params.entry.text}`)
      }
      if (message.method === 'Inspector.targetCrashed') activeErrors.push('Browser renderer crashed')
    })

    for (let index = 0; index < ROUTES.length; index += 1) {
      const route = ROUTES[index]
      const url = new URL(route.query, options.baseUrl).toString()
      activeErrors = []
      const routeStarted = Date.now()
      try {
        if (route.requiresAdmin) {
          await evaluate(cdp, sessionId, "localStorage.setItem('development-actor-role', 'admin')")
        }
        await cdp.send('Page.navigate', { url }, sessionId)
        let snapshot = await waitForPage(cdp, sessionId, route, options.timeoutMs)
        if (await loginIfRequired(cdp, sessionId, options, snapshot)) {
          activeErrors = []
          await cdp.send('Page.navigate', { url }, sessionId)
          snapshot = await waitForPage(cdp, sessionId, route, options.timeoutMs)
        }
        await sleep(400)
        snapshot = await readPageSnapshot(cdp, sessionId, route)
        if (snapshot.loginRequired) throw new Error('Route remained at the login screen')
        if (!isPageReady(route, snapshot)) {
          throw new Error(`Expected visible content ${route.selector}, heading ${route.heading}${route.sectionLabel ? `, section ${route.sectionLabel} with administrator permissions` : ''}; snapshot=${JSON.stringify(snapshot)}`)
        }
        if (activeErrors.length) throw new Error(activeErrors.join(' | '))
        results.push({ name: route.name, url, status: 'PASS', durationMs: Date.now() - routeStarted, ...snapshot })
        console.log(`PASS ${route.name} (${Date.now() - routeStarted} ms)`)
      } catch (error) {
        results.push({ name: route.name, url, status: 'FAIL', durationMs: Date.now() - routeStarted, error: error.message, browserErrors: activeErrors })
        console.error(`FAIL ${route.name}: ${error.message}`)
      }
    }
    removeListener()
  } finally {
    if (cdp) {
      await cdp.send('Browser.close').catch(() => {})
      cdp.close()
    }
    if (!browser.killed) browser.kill()
    await rm(profile, { recursive: true, force: true }).catch(() => {})
  }

  const status = results.every((result) => result.status === 'PASS') ? 'PASS' : 'FAIL'
  const report = { schemaVersion: '1.0', status, baseUrl: options.baseUrl, startedAt, completedAt: new Date().toISOString(), routes: results }
  await mkdir(dirname(options.report), { recursive: true })
  await writeFile(options.report, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
  console.log(`UI smoke report: ${options.report}`)
  if (status !== 'PASS') process.exitCode = 1
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  run().catch((error) => {
    console.error(`UI smoke setup failed: ${error.message}`)
    process.exitCode = 1
  })
}
