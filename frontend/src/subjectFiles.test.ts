import { describe, expect, it } from 'vitest'

import {
  buildSubjectImageReferences,
  createEmptySubjectReferenceFiles,
  getSubjectReferenceCount,
  SUBJECT_IMAGE_ACCEPT,
  validateReferenceBudget,
  validateSubjectReferenceFiles,
} from './subjectFiles'
import type { SubjectReferenceFiles } from './subjectFiles'

function image(name: string, type = 'image/jpeg', size = 1024): File {
  return { name, type, size, lastModified: 1 } as File
}

describe('subject reference files', () => {
  it('requires a frontal image and accepts one to four total images', () => {
    const empty = validateSubjectReferenceFiles(createEmptySubjectReferenceFiles())
    expect(empty.isValid).toBe(false)
    expect(empty.fieldErrors.frontalImage).toContain('正面图')
    expect(empty.errors.join(' ')).toContain('1–4')

    const frontalImage = image('front.jpg')
    const valid = validateSubjectReferenceFiles({
      frontalImage,
      backImage: null,
      detailImages: [],
    })
    expect(valid).toMatchObject({ isValid: true, fileCount: 1 })
  })

  it('accepts WebP references before backend JPEG normalization', () => {
    expect(validateSubjectReferenceFiles({
      frontalImage: image('front.webp', 'image/webp'),
      backImage: image('back.WEBP', ''),
      detailImages: [],
    })).toMatchObject({ isValid: true, fileCount: 2 })
    expect(SUBJECT_IMAGE_ACCEPT).toContain('.webp')
    expect(SUBJECT_IMAGE_ACCEPT).toContain('image/webp')
  })

  it('limits details, file type, file size, total size and duplicate slots', () => {
    const frontalImage = image('front.gif', 'image/gif', 11 * 1024 * 1024)
    const validation = validateSubjectReferenceFiles({
      frontalImage,
      backImage: frontalImage,
      detailImages: [image('a.jpg'), image('b.jpg'), image('c.jpg')],
    })
    expect(validation.isValid).toBe(false)
    expect(validation.fieldErrors.detailImages).toContain('最多')
    expect(validation.errors.join(' ')).toContain('JPG')
    expect(validation.errors.join(' ')).toContain('10 MB')
    expect(validation.errors.join(' ')).toContain('已在其他')

    const totalTooLarge = validateSubjectReferenceFiles({
      frontalImage: image('front.jpg', 'image/jpeg', 10 * 1024 * 1024),
      backImage: image('back.jpg', 'image/jpeg', 10 * 1024 * 1024),
      detailImages: [
        image('side.jpg', 'image/jpeg', 10 * 1024 * 1024),
        image('detail.jpg', 'image/jpeg', 10 * 1024 * 1024 + 1),
      ],
    })
    expect(totalTooLarge.errors.join(' ')).toContain('40 MB')
  })

  it('maps front and supporting images to explicit Kling API roles', () => {
    const files: SubjectReferenceFiles = {
      frontalImage: image('front.jpg'),
      backImage: image('back.jpg'),
      detailImages: [image('detail.png', 'image/png')],
    }
    expect(buildSubjectImageReferences(files).map(({ businessRole, angle, providerRole }) => ({
      businessRole,
      angle,
      providerRole,
    }))).toEqual([
      { businessRole: 'SUBJECT_REFERENCE', angle: 'FRONT', providerRole: 'frontal_image' },
      { businessRole: 'SUBJECT_REFERENCE', angle: 'BACK', providerRole: 'refer_image' },
      { businessRole: 'SUBJECT_REFERENCE', angle: 'SIDE_OR_DETAIL', providerRole: 'refer_image' },
    ])
  })

  it('counts only the active subject mode and validates the seven-reference budget', () => {
    const files: SubjectReferenceFiles = {
      frontalImage: image('front.jpg'),
      backImage: image('back.jpg'),
      detailImages: [],
    }
    expect(getSubjectReferenceCount('none', files, 'element-1')).toBe(0)
    expect(getSubjectReferenceCount('upload', files, 'element-1')).toBe(2)
    expect(getSubjectReferenceCount('history', files, 'element-1')).toBe(1)
    expect(getSubjectReferenceCount('history', files, '')).toBe(0)

    expect(validateReferenceBudget(5, 2)).toMatchObject({
      isValid: true,
      used: 7,
      remaining: 0,
    })
    expect(validateReferenceBudget(6, 2)).toMatchObject({
      isValid: false,
      used: 8,
      remaining: 0,
    })
    expect(validateReferenceBudget(-1, 1).error).toContain('非负整数')
  })
})
