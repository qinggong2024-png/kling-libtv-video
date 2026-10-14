import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Task } from '../../types'
import { GeneratedAssetsView } from './GeneratedAssetsView'

const task = (phase: string, artifact: string | null): Task => ({
  id: `task-${phase}`,
  userId: 'user-1',
  clientTaskId: `client-${phase}`,
  title: `任务 ${phase}`,
  assetCount: 1,
  userRequirement: '',
  analysisModel: 'synthetic',
  generationProvider: 'kling',
  phase,
  phaseReasonCode: null,
  consistencyLevel: null,
  analysisResult: null,
  analysisRunId: null,
  analysisStage: null,
  analysisStartedAt: null,
  analysisHeartbeatAt: null,
  canvasProjectUuid: null,
  stateVersion: 1,
  assets: [{
    id: `asset-${phase}`,
    order: 0,
    required: true,
    originalFilename: 'product.png',
    sha256: 'sha',
    width: 240,
    height: 320,
    thumbnailUrl: '/product.png',
  }],
  variants: [{
    id: `variant-${phase}`,
    kind: 'STABLE',
    revision: 1,
    promptText: 'prompt',
    promptHash: null,
    generationStatus: artifact ? 'SUCCEEDED' : 'RUNNING',
    downloadStatus: artifact ? 'SUCCEEDED' : 'PENDING',
    validationStatus: artifact ? 'PASSED' : 'PENDING',
    finalApprovalStatus: artifact ? 'APPROVED' : 'PENDING',
    qualityGates: {},
    finalApprovedBy: null,
    finalApprovedAt: null,
    humanReviewSeconds: null,
    reviewNotes: null,
    downloadArtifactId: artifact,
    errorCode: null,
    provider: 'kling',
    providerTaskId: null,
    providerStatus: null,
    executionBackend: 'api',
    feedback: null,
    feedbackReasons: [],
    feedbackComment: null,
  }],
  pointsQuota: { dailyLimit: 5, consumed: 0, reserved: 0, uncertain: 0, remaining: 5 },
  actionCapabilities: { canEdit: false, canConfirm: false, canCancel: false, canRetryAnalysis: false, canRegenerate: false, canDownload: false },
  createdAt: '2026-10-14T00:00:00Z',
  updatedAt: '2026-10-14T00:00:00Z',
})

const props = {
  lastSyncedAt: null,
  onOpen: () => {},
  onPlay: () => {},
  onRemix: () => {},
  onFeedbackChanged: () => {},
  onCreateTask: () => {},
}

describe('GeneratedAssetsView', () => {
  it('shows completed artifacts while keeping the task archive as the source of truth', () => {
    const markup = renderToStaticMarkup(<GeneratedAssetsView {...props} tasks={[task('DELIVERABLE', 'artifact-1'), task('GENERATING', null)]} />)

    expect(markup).toContain('生成资产')
    expect(markup).toContain('1 个可查看结果')
    expect(markup).toContain('仅展示逐结果审核通过的媒体')
    expect(markup).toContain('任务 DELIVERABLE')
  })

  it('keeps an actionable empty state when no artifact is available', () => {
    const markup = renderToStaticMarkup(<GeneratedAssetsView {...props} tasks={[]} />)

    expect(markup).toContain('还没有可查看的生成资产')
    expect(markup).toContain('去视频工作室')
  })

  it('retains only approved individual results during partial failure and retry', () => {
    for (const phase of ['PARTIALLY_DELIVERABLE', 'GENERATING']) {
      const source = task(phase, 'approved-artifact')
      source.variants.push({ ...source.variants[0], id: 'pending', finalApprovalStatus: 'PENDING' })
      source.variants.push({ ...source.variants[0], id: 'rejected', finalApprovalStatus: 'REJECTED' })
      const markup = renderToStaticMarkup(<GeneratedAssetsView {...props} tasks={[source]} />)
      expect(markup).toContain('1 个可查看结果')
    }
  })

  it('archives qualified images individually and excludes synthetic candidates', () => {
    const output = { id: 'qualified', kind: 'fusion' as const, view: 'front' as const, label: 'qualified image', url: '/image', downloadUrl: '/image', artifactId: 'image-artifact', qualificationStatus: 'QUALIFIED' as const }
    const markup = renderToStaticMarkup(<GeneratedAssetsView {...props} tasks={[]} imageBatches={[{
      id: 'image-batch', status: 'failed', items: [{ id: 'item', clientTaskId: 'client', outfitId: 'outfit', status: 'failed', providerTaskId: null, providerTaskIds: [], modelId: 'model', outputs: [output, { ...output, id: 'fake', synthetic: true }, { ...output, id: 'pending', qualificationStatus: 'PENDING' }, { ...output, id: 'rejected', qualificationStatus: 'REJECTED' }] }],
    }]} />)
    expect(markup).toContain('1 个可查看结果')
    expect(markup).toContain('来源批次 image-batch')
  })
})
