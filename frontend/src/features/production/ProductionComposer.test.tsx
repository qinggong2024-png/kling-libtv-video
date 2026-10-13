import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ProductionComposer } from './ProductionComposer'
import type { DirectorFixedPreparation } from './productionTypes'

const preparation: DirectorFixedPreparation = {
  schemaVersion: 'director-fixed-offline.v1',
  mode: 'READ_ONLY',
  status: 'READY',
  providerSubmissionAllowed: false,
  qualificationScope: 'OFFLINE_SYNTHETIC_ONLY',
  creativeTaskId: 'creative-task-1',
  packageId: 'storyboard-package-1',
  packageRevision: 4,
  shotId: 'SHOT_01',
  candidateId: 'storyboard-candidate-1',
  sourceImageHash: 'a'.repeat(64),
  shotMapping: {
    shotId: 'SHOT_01',
    order: 1,
    packageId: 'storyboard-package-1',
    candidateId: 'storyboard-candidate-1',
    sourceImageHash: 'a'.repeat(64),
    outputId: 'output-1',
  },
  input: {
    schemaVersion: 'director-fixed-offline.v1',
    source: 'director-studio',
    executionMode: 'director_fixed',
    qualificationScope: 'OFFLINE_SYNTHETIC_ONLY',
    providerSubmissionAllowed: false,
    deliverableEligible: false,
    offlineSyntheticOnly: true,
    creativeTaskId: 'creative-task-1',
    packageId: 'storyboard-package-1',
    packageRevision: 4,
    shotId: 'SHOT_01',
    candidateId: 'storyboard-candidate-1',
    sourceImageHash: 'a'.repeat(64),
    shotMapping: {
      shotId: 'SHOT_01',
      order: 1,
      packageId: 'storyboard-package-1',
      candidateId: 'storyboard-candidate-1',
      sourceImageHash: 'a'.repeat(64),
      outputId: 'output-1',
    },
    immutableSummary: { directionId: 'B' },
  },
  missingFields: [],
  preflight: null,
}

describe('ProductionComposer director_fixed offline boundary', () => {
  it('renders preparation evidence without exposing a generation submit action', () => {
    const markup = renderToStaticMarkup(
      <ProductionComposer
        seed={null}
        directorFixedPreparation={preparation}
        onCreated={() => {}}
        system={null}
        actorId={null}
        layout="studio"
      />,
    )

    expect(markup).toContain('data-execution-mode="director_fixed"')
    expect(markup).toContain('data-provider-submission-allowed="false"')
    expect(markup).toContain('creative-task-1')
    expect(markup).toContain('storyboard-candidate-1')
    expect(markup).toContain('OFFLINE_SYNTHETIC_ONLY')
    expect(markup).not.toContain('开始生成')
    expect(markup).not.toContain('正在准备素材')
  })
})
