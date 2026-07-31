import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createImageGenerationBatch,
  getWaveSpeedConfig,
  setApiUserId,
  updateWaveSpeedConfig,
  verifyWaveSpeedConfig,
} from './api'
import type { ImageGenerationClientManifest } from './types'

const USER_ID = '00000000-0000-0000-0000-000000000001'
const ADMIN_ID = '00000000-0000-0000-0000-000000000099'

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('WaveSpeed API contracts', () => {
  beforeEach(() => {
    vi.stubGlobal('window', globalThis)
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => jsonResponse({
      enabled: true,
      apiKeyConfigured: true,
      credentialSource: 'admin',
      baseUrl: 'https://api.wavespeed.ai/api/v3',
      status: 'READY',
      available: true,
      checkedAt: null,
    })))
    setApiUserId(USER_ID)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('keeps administrator config and verification calls scoped to the administrator', async () => {
    await getWaveSpeedConfig(ADMIN_ID)
    await updateWaveSpeedConfig(ADMIN_ID, { enabled: true, apiKey: 'new-secret-key' })
    await verifyWaveSpeedConfig(ADMIN_ID)

    const calls = vi.mocked(fetch).mock.calls
    expect(calls.map(([input]) => String(input))).toEqual([
      '/api/v1/admin/wavespeed/config',
      '/api/v1/admin/wavespeed/config',
      '/api/v1/admin/wavespeed/verify',
    ])
    expect(calls.map(([, init]) => new Headers(init?.headers).get('X-User-Id'))).toEqual([
      ADMIN_ID,
      ADMIN_ID,
      ADMIN_ID,
    ])
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ enabled: true, apiKey: 'new-secret-key' })
  })

  it('submits an idempotent multipart batch with explicit paid consent', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ id: 'batch-remote', status: 'QUEUED', items: [] }, 201))
    const manifest: ImageGenerationClientManifest = {
      clientBatchId: 'batch-client',
      name: '夏季新品',
      provider: 'gpt',
      modes: ['fusion'],
      resultCount: 1,
      aspectRatio: '9:16',
      resolution: '2k',
      quality: 'medium',
      outputFormat: 'png',
      allowBackInference: true,
      paidSubmissionConsent: true,
      expectedGenerationCount: 1,
      items: [{
        clientTaskId: 'task-client',
        outfitId: 'outfit-1',
        outfitName: '套装 01',
        sku: 'SKU-1',
        prompts: { fusion: '保持服装准确', storyboard: '' },
        storyboardShots: [],
        referenceFileIndexes: [0, 1],
        referenceRoles: [
          { fileIndex: 0, role: 'model.front' },
          { fileIndex: 1, role: 'product.front' },
        ],
      }],
    }

    await createImageGenerationBatch(manifest, [
      new File(['model'], 'model.jpg', { type: 'image/jpeg' }),
      new File(['product'], 'product.jpg', { type: 'image/jpeg' }),
    ])

    const call = vi.mocked(fetch).mock.calls[0]
    const headers = new Headers(call[1]?.headers)
    expect(String(call[0])).toBe('/api/v1/image-generation-batches')
    expect(headers.get('Idempotency-Key')).toBe('batch-client')
    expect(headers.has('Content-Type')).toBe(false)
    expect(call[1]?.body).toBeInstanceOf(FormData)
    const body = call[1]?.body as FormData
    expect(JSON.parse(String(body.get('clientManifest')))).toEqual(manifest)
    expect(body.getAll('files')).toHaveLength(2)
  })
})
