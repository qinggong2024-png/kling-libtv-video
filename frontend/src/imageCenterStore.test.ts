import { afterEach, describe, expect, it, vi } from 'vitest'
import { imageCenterDraftKey, loadImageCenterDraft, saveImageCenterDraft } from './imageCenterStore'
import { createImageCenterDraft } from './imageCenterModel'

afterEach(() => vi.unstubAllGlobals())

describe('account-scoped image drafts', () => {
  it('keeps accounts separate and never uses the unowned legacy key', () => {
    expect(imageCenterDraftKey('A')).toBe('image-center:v2:A')
    expect(imageCenterDraftKey('B')).not.toBe(imageCenterDraftKey('A'))
    expect(imageCenterDraftKey('A')).not.toBe('active')
  })

  it('does not open storage for anonymous or blank identities', async () => {
    const open = vi.fn()
    vi.stubGlobal('indexedDB', { open })
    for (const scope of [null, undefined, '', '  ']) {
      expect(await loadImageCenterDraft(scope)).toBeNull()
      await saveImageCenterDraft(scope, createImageCenterDraft('draft', 'outfit'))
    }
    expect(open).not.toHaveBeenCalled()
  })
})
