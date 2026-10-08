import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'
import { collectPageSnapshot, isPageReady, ROUTES } from './ui-smoke.mjs'

const records = ROUTES.find((route) => route.name === 'records')
const adminRoutes = ROUTES.filter((route) => route.requiresAdmin)
test('provider section label matches the actual application navigation', () => {
  assert.equal(ROUTES.find(route => route.name === 'admin-providers').sectionLabel, '\u751f\u6210\u63d0\u4f9b\u5546')
})
const ready = (route, overrides = {}) => ({
  readyState: 'complete',
  rootChildren: 1,
  bodyTextLength: 100,
  targetFound: true,
  targetVisible: true,
  pageHeading: route.heading,
  activeSection: route.sectionLabel ?? '',
  adminRole: '\u7ba1\u7406\u5458\u6743\u9650',
  permissionDenied: false,
  loginRequired: false,
  ...overrides,
})

test('every configured route accepts its matching rendered snapshot', () => {
  for (const route of ROUTES) assert.equal(isPageReady(route, ready(route)), true, route.name)
})

test('records cannot pass with just an existing generic or hidden page', () => {
  assert.notEqual(records.selector, '.page-view')
  for (const overrides of [
    { targetFound: false },
    { targetVisible: false },
    { pageHeading: '\u56fe\u7247\u4e2d\u5fc3' },
    { pageHeading: '' },
  ]) assert.equal(isPageReady(records, ready(records, overrides)), false)
})

test('incomplete, empty, unauthenticated and denied snapshots fail closed', () => {
  assert.equal(isPageReady(records, null), false)
  assert.equal(isPageReady(records, {}), false)
  for (const overrides of [
    { readyState: 'loading' }, { rootChildren: 0 }, { bodyTextLength: 20 },
    { loginRequired: true }, { permissionDenied: true },
  ]) assert.equal(isPageReady(records, ready(records, overrides)), false)
})

test('each admin route requires its own visible section, title and administrator role', () => {
  for (const route of adminRoutes) {
    assert.notEqual(route.selector, '.admin-view .admin-section-content > *')
    for (const overrides of [
      { targetVisible: false }, { targetFound: false }, { pageHeading: records.heading },
      { activeSection: '' }, { activeSection: 'wrong section' },
      { adminRole: '\u8fd0\u8425\u6743\u9650' }, { adminRole: '' },
      { permissionDenied: true },
    ]) assert.equal(isPageReady(route, ready(route, overrides)), false, route.name)
    for (const other of adminRoutes.filter((other) => other !== route)) {
      assert.equal(isPageReady(route, ready(route, { activeSection: other.sectionLabel })), false)
    }
  }
})

function element(textContent = '', options = {}) {
  return {
    textContent,
    parentElement: null,
    hidden: false,
    style: { display: 'block', visibility: 'visible', opacity: '1', contentVisibility: 'visible' },
    getAttribute: () => null,
    getClientRects: () => [{ width: 100, height: 20 }],
    ...options,
  }
}

function fixture(route, options = {}) {
  const heading = element(route.heading)
  const section = element(route.sectionLabel ?? '')
  const role = element(options.role ?? '\u7ba1\u7406\u5458\u6743\u9650')
  const page = element()
  page.querySelectorAll = (selector) => ({
    h1: [heading],
    '.subnav-tabs button[aria-current="page"] strong': [section],
    '.system-health small': [role],
  })[selector] ?? []
  const target = element('', { parentElement: page, closest: () => page })
  for (const child of [heading, section, role]) child.parentElement = page
  const denial = element(options.denial ?? '')
  const document = {
    readyState: 'complete',
    title: 'fixture',
    body: { innerText: 'Offline fixture with sufficient rendered body text' },
    getElementById: () => ({ childElementCount: 1 }),
    querySelectorAll: (selector) => {
      if (selector === route.selector) return options.targets ?? [target]
      if (selector === '.page-view .empty-state > strong') return options.denial ? [denial] : []
      if (selector === '.login-view') return options.login ? [options.login] : []
      return []
    },
  }
  const snapshot = () => runInNewContext(`(${collectPageSnapshot.toString()})(${JSON.stringify(route)})`, {
    document,
    getComputedStyle: (node) => node.style,
  })
  return { snapshot, target, page, heading, section, denial }
}

test('collector rejects hidden targets and hidden ancestors, CSS hiding and zero-sized targets', () => {
  const mutations = [
    (f) => { f.target.hidden = true },
    (f) => { f.page.hidden = true },
    (f) => { f.page.style.display = 'none' },
    (f) => { f.target.style.visibility = 'hidden' },
    (f) => { f.page.style.visibility = 'collapse' },
    (f) => { f.page.style.opacity = '0' },
    (f) => { f.page.style.contentVisibility = 'hidden' },
    (f) => { f.page.getAttribute = () => 'true' },
    (f) => { f.target.getClientRects = () => [] },
    (f) => { f.target.getClientRects = () => [{ width: 0, height: 20 }] },
  ]
  for (const mutate of mutations) {
    const f = fixture(records)
    mutate(f)
    assert.equal(f.snapshot().targetFound, true)
    assert.equal(f.snapshot().targetVisible, false)
    assert.equal(isPageReady(records, f.snapshot()), false)
  }
})

test('collector uses the visible matching target instead of the first hidden match', () => {
  const hidden = element('', { hidden: true })
  const f = fixture(records)
  const visible = fixture(records, { targets: [hidden, f.target] })
  assert.equal(isPageReady(records, visible.snapshot()), true)
})

test('collector requires a visible heading and visible current admin label', () => {
  const f = fixture(adminRoutes[0])
  assert.equal(isPageReady(adminRoutes[0], f.snapshot()), true)
  f.heading.hidden = true
  assert.equal(isPageReady(adminRoutes[0], f.snapshot()), false)
  f.heading.hidden = false
  f.section.hidden = true
  assert.equal(isPageReady(adminRoutes[0], f.snapshot()), false)
})

test('visible permission messages and operator-only content do not pass admin smoke', () => {
  for (const route of adminRoutes) {
    assert.equal(isPageReady(route, fixture(route, { role: '\u8fd0\u8425\u6743\u9650' }).snapshot()), false)
    for (const denial of ['\u6ca1\u6709\u7ba1\u7406\u4e2d\u5fc3\u6743\u9650', '\u9700\u8981\u7ba1\u7406\u5458\u6743\u9650', '\u51ed\u636e\u7531\u7ba1\u7406\u5458\u7ef4\u62a4']) {
      const f = fixture(route, { denial })
      assert.equal(f.snapshot().permissionDenied, true)
      assert.equal(isPageReady(route, f.snapshot()), false)
      f.denial.hidden = true
      assert.equal(isPageReady(route, f.snapshot()), true)
    }
  }
})

test('hidden login is ignored but visible login blocks a matching page', () => {
  const login = element('', { hidden: true })
  const f = fixture(records, { login })
  assert.equal(isPageReady(records, f.snapshot()), true)
  login.hidden = false
  assert.equal(isPageReady(records, f.snapshot()), false)
})
