import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { DirectorApiError, type DirectorTaskResponse } from './directorApi'
import { createDirectorDraft } from './directorModel'
import { toCreativeBrief } from './directorAdapters'
import { prepareProductionBridge } from './productionBridge'
import { DirectorBriefSummary, DirectorBridgeStatus, DirectorPackageEvidence } from './DirectorPlanningViews'
import { explainDirectorFailure, selectDirectorBriefSummary, selectDirectorBridgeExplanation, selectDirectorDirectionCards, selectDirectorPackageEvidence } from './directorPresentation'

function task(): DirectorTaskResponse {
  return {
    id: 'task-1', mode: 'OFFLINE_FAKE_ONLY', status: 'PLAN_READY', state_version: 3,
    snapshot: {
      asset: { sha256: 'source-sha', width: 240, height: 320, object_key: 'not-a-url' },
      trace: [], candidates: [], calls: 0, cost_micros: 0, total_calls: 0, total_cost_micros: 0,
      plan: { directions: [{ id: 'B', scene: 'server scene B', behavior: 'server behavior B' }], selected_direction: 'B' },
      package: {
        package_id: 'root-package', revision: 3, parent_package_id: null, locks_hash: 'locks',
        facts_revision: 2, preservation_hash: 'preservation', ruleset: 'rules-v1',
        shot_id: 'FIRST_FRAME', prompt: 'server prompt\npreserve fabric',
        reality: [{ dimension: 'fabric', decision: 'retain', evidence: 'server evidence' }],
      },
      storyboard: {
        packages: {
          SHOT_01: {
            package_id: 'shot-package', revision: 4, parent_package_id: 'root-package',
            locks_hash: 'shot-locks', facts_revision: 2, preservation_hash: 'shot-preservation',
            ruleset: 'rules-v1', purpose: 'VIDEO_STORYBOARD', shot_id: 'SHOT_01', prompt: 'shot prompt', reality: [],
          },
        },
        candidates: [], selections: {}, latest_reviews: {},
      },
    },
  }
}

function bridge() {
  return prepareProductionBridge({
    source: 'director-studio', projectId: 'project-1', directionId: 'B', packageId: 'root-package', packageRevision: 3,
    shotId: 'FIRST_FRAME', references: { productFront: true, selectedDirection: true, productionPackage: true },
  })!
}

describe('Director UX read-only projections', () => {
  it('summarizes brief values without inventing objectives or audience', () => {
    const draft = createDirectorDraft()
    draft.intake.productName = '  Jacket  '
    const brief = toCreativeBrief(draft.intake)
    expect(selectDirectorBriefSummary(brief)).toEqual([
      { label: '商品', value: 'Jacket' }, { label: '品牌', value: '通用风格' },
      { label: '创作目标', value: '未填写' }, { label: '目标受众', value: '未填写' }, { label: '保留要求', value: '未填写' },
    ])
    expect(brief.productName).toBe('  Jacket  ')
    const markup = renderToStaticMarkup(<DirectorBriefSummary brief={brief} />)
    expect(markup).toContain('未纳入当前离线分析请求或服务端生产包')
  })

  it('does not imply a confirmed brand when none was supplied', () => {
    const draft = createDirectorDraft()
    draft.intake.brandMode = 'brand'
    expect(selectDirectorBriefSummary(toCreativeBrief(draft.intake))[1].value).toBe('未填写品牌')
  })

  it('projects direction cards without confirming before a package exists', () => {
    const draft = createDirectorDraft()
    const cards = selectDirectorDirectionCards(null, draft)
    expect(cards).toHaveLength(3)
    expect(cards.every((card) => !card.selected && !card.confirmed)).toBe(true)
    expect(cards[0]).toMatchObject({
      title: '干净街拍',
      summary: '把商品细节放在自然行走和城市光线里。',
      scene: '城市街角',
      behavior: '回身看镜头',
      camera: '中近景跟拍',
      emotion: '轻松自信',
    })
  })

  it('keeps selected and confirmed direction state separate', () => {
    const workflow = task()
    const draft = createDirectorDraft()
    draft.selectedDirectionId = 'B'
    const before = structuredClone(workflow)
    const cards = selectDirectorDirectionCards(workflow, draft)
    expect(cards.find((card) => card.id === 'B')).toMatchObject({ selected: true, confirmed: true })
    expect(cards.find((card) => card.id === 'A')).toMatchObject({ selected: false, confirmed: false })
    expect(workflow).toEqual(before)
  })

  it('preserves exact package evidence and keeps FIRST_FRAME and SHOT_01 independent', () => {
    const workflow = task()
    expect(selectDirectorPackageEvidence(workflow, 'FIRST_FRAME')).toBe(workflow.snapshot.package)
    expect(selectDirectorPackageEvidence(workflow, 'SHOT_01')).toBe(workflow.snapshot.storyboard?.packages.SHOT_01)
    expect(selectDirectorPackageEvidence(null, 'FIRST_FRAME')).toBeNull()
    const markup = renderToStaticMarkup(<DirectorPackageEvidence workflow={workflow} shotId="SHOT_01" />)
    expect(markup).toContain('shot-package')
    expect(markup).toContain('root-package')
    expect(markup).toContain('r4')
    expect(markup).toContain('shot-locks')
    expect(markup).toContain('shot-preservation')
    expect(markup).not.toContain('server prompt')
  })

  it('renders immutable Prompt and Reality as text rather than editable or executable HTML', () => {
    const workflow = task()
    workflow.snapshot.package!.prompt = '<img src=x onerror=alert(1)>\noriginal prompt'
    const markup = renderToStaticMarkup(<DirectorPackageEvidence workflow={workflow} shotId="FIRST_FRAME" />)
    expect(markup).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(markup).toContain('server evidence')
    expect(markup).not.toContain('<textarea')
    expect(markup).not.toContain('<img')
  })

  it('renders missing package and absent Reality evidence without fabricating revisions or decisions', () => {
    expect(renderToStaticMarkup(<DirectorPackageEvidence workflow={null} shotId="SHOT_01" />)).toContain('暂无服务端生产包')
    const workflow = task()
    workflow.snapshot.package!.reality = []
    expect(renderToStaticMarkup(<DirectorPackageEvidence workflow={workflow} shotId="FIRST_FRAME" />)).toContain('尚无服务端 Reality 决策')
  })

  it('uses the existing bridge blockers and never turns unverified checks into success or failure', () => {
    const preparation = bridge()
    const before = structuredClone(preparation)
    const result = selectDirectorBridgeExplanation(preparation, task())!
    expect(result.checks).toHaveLength(10)
    expect(result.checks.every((check) => check.status === '待服务端验证')).toBe(true)
    expect(result.blockingReasons).toBe(preparation.blockingReasons)
    expect(result.nextSteps.map((step) => step.code)).toEqual(preparation.nextSteps)
    expect(preparation).toEqual(before)
    const markup = renderToStaticMarkup(<DirectorBridgeStatus preparation={preparation} workflow={task()} />)
    expect(markup).toContain('PREFLIGHT_REQUIRED')
    expect(markup).toContain('禁止 Provider submission')
    expect(markup).toContain('OFFLINE_SYNTHETIC_ONLY 不可交付')
    expect(markup).toContain('待验证不等于验证失败')
    for (const reason of preparation.blockingReasons) {
      expect(markup).toContain(reason.message)
    }
    expect(markup).not.toContain('<button')
    expect(preparation.providerSubmissionAllowed).toBe(false)
  })

  it('does not create a second bridge or checks before handoff exists', () => {
    expect(selectDirectorBridgeExplanation(null, task())).toBeNull()
    const markup = renderToStaticMarkup(<DirectorBridgeStatus preparation={null} workflow={null} />)
    expect(markup).toContain('未执行生产预检')
    expect(markup).not.toContain('待服务端验证')
  })

  it.each(['UNKNOWN', 'WRITE_UNCERTAIN'])('preserves %s without suggesting a production retry', (state) => {
    const workflow = task()
    workflow.snapshot.execution_state = state
    const explanation = selectDirectorBridgeExplanation(bridge(), workflow)!
    expect(explanation.executionWarning).toContain(state)
    expect(explanation.executionWarning).toContain('禁止自动重投')
    expect(workflow.snapshot.execution_state).toBe(state)
  })

  it('preserves stop evidence as a read-only explanation', () => {
    const workflow = task()
    workflow.snapshot.stopped = true
    workflow.snapshot.stop_reason = 'revoked source'
    expect(selectDirectorBridgeExplanation(bridge(), workflow)?.executionWarning).toContain('revoked source')
    expect(workflow.snapshot.stopped).toBe(true)
  })

  it.each(['STALE_VERSION', 'AUTHORIZATION_EXPIRED', 'ASSET_HASH_MISMATCH', 'EXECUTION_UNKNOWN', 'PAID_MODE_NOT_ALLOWED'])('explains %s and preserves raw error message/code', (code) => {
    const text = explainDirectorFailure(new DirectorApiError(409, code, 'original message'), 'fallback')
    expect(text).toContain('original message')
    expect(text).toContain(`[${code}]`)
    expect(text).not.toContain('fallback')
  })

  it('preserves an unknown error code, refuses inferred retry, and respects non-API fallback', () => {
    const text = explainDirectorFailure(new DirectorApiError(400, 'FUTURE_REASON', 'raw message'), 'fallback')
    expect(text).toContain('[FUTURE_REASON]')
    expect(text).toContain('不推断成功或自动重试')
    expect(explainDirectorFailure(new Error('network'), 'fallback')).toBe('fallback')
  })
})
