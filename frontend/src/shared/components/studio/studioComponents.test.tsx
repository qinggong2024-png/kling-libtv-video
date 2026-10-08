import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Task, VideoTemplateSummary } from '../../../types'
import { Button, IconButton } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { AssetCard } from '../assets/AssetCard'
import { TaskCard } from '../tasks/TaskCard'
import { TemplateCard, TemplateSelector, RecipePreview } from './TemplateSelector'
import { CreativeCanvas } from './CreativeCanvas'
import { Storyboard } from './Storyboard'

const template: VideoTemplateSummary = {
  id: 'real-template-id', version: '1', name: '服装展示', description: '登记配方',
  status: 'active', minImages: 1, maxImages: 7,
  defaultSettings: { durationSeconds: 5, ratio: '9:16', sound: false, subtitles: false, smartStoryboard: false, continuityStrategy: 'explicit_cuts' },
  actionPresets: { turn: { label: '侧身', instruction: '缓慢转身并停稳' } },
  cameraPresets: {}, tempoPresets: {}, sourceNote: '来源记录',
}

describe('studio shared components', () => {
  it('disables a busy button and names icon controls', () => {
    expect(renderToStaticMarkup(<Button busy>准备素材</Button>)).toContain('disabled=""')
    const markup = renderToStaticMarkup(<IconButton label="重置缩放">R</IconButton>)
    expect(markup).toContain('aria-label="重置缩放"')
    expect(markup).toContain('title="重置缩放"')
  })
  it('keeps asset selection explicit without review side effects', () => {
    const markup = renderToStaticMarkup(<AssetCard name="产品图" selected onSelect={() => {}} />)
    expect(markup).toContain('aria-pressed="true"')
    expect(markup).not.toContain('已合格')
  })
  it('uses the template contract and does not invent missing camera presets', () => {
    const markup = renderToStaticMarkup(<RecipePreview template={template} />)
    expect(markup).toContain('缓慢转身并停稳')
    expect(markup).toContain('未配置')
    expect(markup).toContain('5 秒')
    expect(renderToStaticMarkup(<TemplateCard template={template} onPreview={() => {}} />)).toContain('查看配方')
    const selector = renderToStaticMarkup(<TemplateSelector templates={[template]} value={template.id} onChange={() => {}} />)
    expect(selector).toContain(`value="${template.id}"`)
    expect(selector).toContain('selected=""')
  })
  it('has a stable empty canvas and disabled media controls', () => {
    const markup = renderToStaticMarkup(<CreativeCanvas onPreview={() => {}} />)
    expect(markup).toContain('暂无分镜')
    expect(markup).toContain('aria-label="画布缩放"')
    expect(markup).toContain('disabled=""')
    expect(markup).not.toContain('9:16')
  })
  it('offers keyboard reorder controls with boundary limits', () => {
    const materials = [{ id: 'a', file: { name: 'a.png' } as File }, { id: 'b', file: { name: 'b.png' } as File }]
    const markup = renderToStaticMarkup(<Storyboard materials={materials} selectedId="a" onSelect={() => {}} onMove={() => {}} onRemove={() => {}} onDropAt={() => {}} onPreview={() => {}} />)
    expect(markup).toContain('前移分镜 1')
    expect(markup).toContain('后移分镜 2')
    expect(markup.match(/disabled=""/g)).toHaveLength(2)
    expect(markup.match(/aria-label="查看图片 /g)).toHaveLength(2)
    expect(markup).toContain('删除图片 1')
    expect(markup).toContain('draggable="true"')
  })
  it('locks storyboard mutations but preserves read-only batch inspection', () => {
    const materials = [{ id: 'a', file: { name: 'a.png' } as File }]
    const markup = renderToStaticMarkup(<Storyboard materials={materials} disabled onSelect={() => {}} onMove={() => {}} onRemove={() => {}} onDropAt={() => {}} onPreview={() => {}} />)
    expect(markup).toContain('draggable="false"')
    expect(markup).toContain('tabindex="0"')
    expect(markup.match(/disabled=""/g)).toHaveLength(3)
  })
  it('does not reserve a large empty source preview', () => {
    const markup = renderToStaticMarkup(<Storyboard materials={[]} onSelect={() => {}} onMove={() => {}} onRemove={() => {}} onDropAt={() => {}} onPreview={() => {}} />)
    expect(markup).toContain('暂无分镜')
    expect(markup).not.toContain('studio-canvas')
    expect(markup).not.toContain('material-preview')
  })
  it('renders actual task uncertainty rather than claiming completion', () => {
    const task: Task = {
      id: 'unknown-task', userId: 'fixture-user', clientTaskId: 'fixture-client', title: '任务',
      assetCount: 0, userRequirement: '', analysisModel: '', generationProvider: '',
      phase: 'DELIVERABLE', phaseReasonCode: null, consistencyLevel: null, analysisResult: null,
      analysisRunId: null, analysisStage: null, analysisStartedAt: null, analysisHeartbeatAt: null,
      canvasProjectUuid: null, stateVersion: 1, assets: [],
      createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
      pointsQuota: { dailyLimit: 0, consumed: 0, reserved: 0, uncertain: 0, remaining: 0 },
      actionCapabilities: { canDownload: false, canConfirm: false, canEdit: false, canCancel: false, canRetryAnalysis: false, canRegenerate: false },
      variants: [{
        id: 'unknown-variant', kind: 'STABLE', revision: 1, promptText: '', promptHash: null,
        generationStatus: 'UNKNOWN', downloadStatus: 'PENDING', validationStatus: 'PENDING',
        finalApprovalStatus: 'PENDING', qualityGates: {}, finalApprovedBy: null, finalApprovedAt: null,
        humanReviewSeconds: null, reviewNotes: null, downloadArtifactId: null, errorCode: null,
        provider: 'fixture', providerTaskId: null, providerStatus: null, executionBackend: null,
        feedback: null, feedbackReasons: [], feedbackComment: null,
      }],
    }
    const markup = renderToStaticMarkup(<TaskCard task={task} onOpen={() => {}} />)
    expect(markup).toContain('data-studio-status="attention"')
    expect(markup).not.toContain('已完成')
  })
  it('uses a native modal container to support nested media previews', () => {
    const markup = renderToStaticMarkup(<Modal labelledBy="title" onClose={() => {}}><h2 id="title">视频预览</h2></Modal>)
    expect(markup).toContain('<dialog')
    expect(markup).toContain('aria-labelledby="title"')
  })
})
