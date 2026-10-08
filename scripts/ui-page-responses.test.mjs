import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { createPageResponses } from './fixtures/ui-page-responses.mjs'
import { createAdminResponses } from './fixtures/ui-admin-responses.mjs'

test('synthetic task phases match the actual parent task contract', async () => {
  const contract = JSON.parse(await readFile(new URL('../backend/contracts/state-machines.json',import.meta.url),'utf8'))
  const phases = new Set(Object.keys(contract.parentTask.transitions))
  const tasks = createPageResponses().get('/api/v1/tasks')
  assert.equal(tasks.length,3)
  for (const task of tasks) assert(phases.has(task.phase),`Unrecognized parent phase: ${task.phase}`)
  assert.equal(tasks.filter(task => task.phase === 'DELIVERABLE').length,1)
  assert.equal(tasks.filter(task => task.phase === 'ACTION_REQUIRED').length,1)
})

test('empty fixtures really remove task, catalog and template data', () => {
  const responses = createPageResponses({empty:true})
  for (const path of ['tasks','video-templates','site-style-profiles','motion-actions']) {
    assert.deepEqual(responses.get(`/api/v1/${path}`),[])
  }
})

test('role fixtures have no live identity or enabled generation channel', () => {
  for (const role of ['ADMIN','OPERATOR','USER']) {
    const responses = createPageResponses({role})
    assert.equal(responses.get('/api/v1/auth/me').role,role)
    const status = responses.get('/api/v1/system/status')
    assert.equal(status.environment,'test')
    assert.equal(status.videoGeneration.enabled,false)
    assert.equal(status.videoGeneration.authenticated,false)
    assert.equal(status.videoGeneration.available,false)
    assert.equal(status.openaiConfigured,false)
    assert.equal(status.libtvConfigured,false)
  }
})

test('admin fixtures expose arrays and complete disabled configurations, never secrets', () => {
  const responses = createAdminResponses()
  assert(Array.isArray(responses.get('/api/v1/admin/users')))
  assert.equal(responses.get('/api/v1/admin/operations').runtime.config.globalPaused,true)
  assert.equal(responses.get('/api/v1/admin/operations').runtime.config.paidSubmissionsPaused,true)
  for (const name of ['kling','wavespeed','bach']) {
    const config = responses.get(`/api/v1/admin/${name}/config`)
    assert.equal(config.enabled,false)
    assert.equal(config.authenticated,false)
    assert.equal(new URL(config.baseUrl).hostname,'example.invalid')
    for (const secret of ['apiKey','accessKey','secretKey']) assert.equal(secret in config,false)
  }
})
