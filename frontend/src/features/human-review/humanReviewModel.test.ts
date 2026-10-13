import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { HumanReviewInput, HumanReviewQuery, HumanReviewReason, HumanReviewSubjectType } from './contracts'
import {
  humanReviewInputError,
  humanReviewQueryString,
  humanReviewReasons,
  persistPendingHumanReview,
  readPendingHumanReview,
} from './humanReviewModel'

const outputHash = 'a'.repeat(64)
const imageQuery: HumanReviewQuery = { subjectType: 'IMAGE_OUTPUT', subjectId: 'image-1' }
const directorQuery: HumanReviewQuery = {
  subjectType: 'DIRECTOR_CANDIDATE', subjectId: 'candidate-1', taskId: 'director-1',
}
const subjectTypes: HumanReviewSubjectType[] = [
  'IMAGE_OUTPUT', 'DIRECTOR_CANDIDATE', 'VIDEO_VARIANT',
]

function createMemoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() { return data.size },
    clear() { data.clear() },
    getItem(key) { return data.get(String(key)) ?? null },
    key(index) { return [...data.keys()][index] ?? null },
    removeItem(key) { data.delete(String(key)) },
    setItem(key, value) { data.set(String(key), String(value)) },
  }
}

function input(overrides: Partial<HumanReviewInput> = {}): HumanReviewInput {
  return {
    ...imageQuery, reviewKey: 'review-1', expectedOutputHash: outputHash,
    verdict: 'FAIL', reasonCodes: ['GARMENT'], note: '', ...overrides,
  }
}

function storeRaw(raw: string): void {
  expect(persistPendingHumanReview(imageQuery, input())).toBe(true)
  const key = sessionStorage.key(0)
  if (key === null) throw new Error('pending entry was not persisted')
  sessionStorage.setItem(key, raw)
}

function storeEnvelope(value: unknown): void {
  storeRaw(JSON.stringify(value))
}

beforeEach(() => {
  vi.stubGlobal('sessionStorage', createMemoryStorage())
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('human review media rules', () => {
  it.each(subjectTypes)('%s exposes exactly the reasons for that medium', (subjectType) => {
    const expected = subjectType === 'VIDEO_VARIANT'
      ? ['MOTION', 'DEFORMATION', 'CAMERA', 'OTHER']
      : ['FACE', 'GARMENT', 'REALISM', 'SPACE', 'LIGHTING', 'OTHER']
    const reasons = humanReviewReasons(subjectType)
    expect(reasons.map(([code]) => code)).toEqual(expected)
    expect(reasons.every(([, label]) => label.trim().length > 0)).toBe(true)
    for (const reason of expected) {
      expect(humanReviewInputError(input({
        subjectType, taskId: subjectType === 'DIRECTOR_CANDIDATE' ? 'director-1' : undefined,
        reasonCodes: [reason as HumanReviewReason],
        note: reason === 'OTHER' ? 'A concrete issue' : '',
      }))).toBeNull()
    }
  })

  it.each([
    ['IMAGE_OUTPUT', 'MOTION'], ['IMAGE_OUTPUT', 'DEFORMATION'], ['IMAGE_OUTPUT', 'CAMERA'],
    ['DIRECTOR_CANDIDATE', 'MOTION'], ['VIDEO_VARIANT', 'FACE'], ['VIDEO_VARIANT', 'GARMENT'],
    ['VIDEO_VARIANT', 'REALISM'], ['VIDEO_VARIANT', 'SPACE'], ['VIDEO_VARIANT', 'LIGHTING'],
  ] as const)('rejects %s with the %s reason', (subjectType, reason) => {
    expect(humanReviewInputError(input({
      subjectType, taskId: 'director-1', reasonCodes: [reason],
    }))).toBe('原因与媒介类型不匹配')
  })

  it.each(['IMAGE_OUTPUT', 'DIRECTOR_CANDIDATE'] as const)(
    '%s permits image REWORK with a reason', (subjectType) => {
      expect(humanReviewInputError(input({
        subjectType, taskId: 'director-1', verdict: 'REWORK',
      }))).toBeNull()
    },
  )

  it('rejects video REWORK even with a valid video reason', () => {
    expect(humanReviewInputError(input({
      subjectType: 'VIDEO_VARIANT', verdict: 'REWORK', reasonCodes: ['MOTION'],
    }))).toBe('视频评价不支持 REWORK')
  })

  it.each(subjectTypes)('%s PASS accepts notes but rejects failure reasons', (subjectType) => {
    const pass = input({
      subjectType, taskId: 'director-1', verdict: 'PASS', reasonCodes: [], note: 'Looks usable',
    })
    expect(humanReviewInputError(pass)).toBeNull()
    expect(humanReviewInputError({ ...pass, reasonCodes: ['OTHER'] }))
      .toBe('PASS 不包含失败原因')
  })

  it.each(['FAIL', 'REWORK'] as const)('%s requires at least one reason', (verdict) => {
    expect(humanReviewInputError(input({ verdict, reasonCodes: [] })))
      .toBe('请选择至少一个原因')
  })

  it.each(['', ' ', '\t\n'])('OTHER rejects a blank explanation %j', (note) => {
    expect(humanReviewInputError(input({ reasonCodes: ['GARMENT', 'OTHER'], note })))
      .toBe('OTHER 需要填写说明')
  })

  it('accepts OTHER with an explanation and enforces the 255-character boundary', () => {
    expect(humanReviewInputError(input({ reasonCodes: ['OTHER'], note: 'A specific issue' })))
      .toBeNull()
    expect(humanReviewInputError(input({ note: 'x'.repeat(255) }))).toBeNull()
    expect(humanReviewInputError(input({ note: 'x'.repeat(256) }))).toBe('说明最多 255 字符')
  })
})

describe('human review task and output binding', () => {
  it.each(['', 'a'.repeat(63), 'a'.repeat(65), 'A'.repeat(64), 'g'.repeat(64), ` ${outputHash}`])(
    'rejects an unconfirmed or malformed output hash %j', (expectedOutputHash) => {
      expect(humanReviewInputError(input({ expectedOutputHash }))).toBe('结果指纹尚未确认')
    },
  )

  it('requires a director task while image and video subjects need no director task', () => {
    expect(humanReviewInputError(input({ subjectType: 'DIRECTOR_CANDIDATE' })))
      .toBe('缺少导演任务')
    expect(humanReviewInputError(input({ ...directorQuery, taskId: '' })))
      .toBe('缺少导演任务')
    expect(humanReviewInputError(input(directorQuery))).toBeNull()
    expect(humanReviewInputError(input())).toBeNull()
    expect(humanReviewInputError(input({
      subjectType: 'VIDEO_VARIANT', reasonCodes: ['CAMERA'],
    }))).toBeNull()
  })

  it('encodes query values without allowing a subject to inject query parameters', () => {
    const query: HumanReviewQuery = {
      ...directorQuery, subjectId: 'candidate & taskId=wrong/+?', taskId: 'task & other=value',
    }
    const parsed = new URLSearchParams(humanReviewQueryString(query))
    expect(Array.from(parsed.keys())).toEqual(['subjectType', 'subjectId', 'taskId'])
    expect(parsed.get('subjectId')).toBe(query.subjectId)
    expect(parsed.get('taskId')).toBe(query.taskId)
    expect(new URLSearchParams(humanReviewQueryString(imageQuery)).has('taskId')).toBe(false)
  })
})

describe('pending human review recovery', () => {
  it('restores the original review key, hash and payload as a detached snapshot', () => {
    const original = input({ ...directorQuery, reasonCodes: ['GARMENT', 'LIGHTING'] })
    const before = structuredClone(original)
    expect(persistPendingHumanReview(directorQuery, original)).toBe(true)
    expect(original).toEqual(before)
    original.reasonCodes.push('FACE')
    original.expectedOutputHash = 'b'.repeat(64)
    const restored = readPendingHumanReview(directorQuery)
    expect(restored).toEqual(before)
    expect(restored).not.toBe(original)
    expect(restored?.reviewKey).toBe('review-1')
    expect(restored?.expectedOutputHash).toBe(outputHash)
    restored?.reasonCodes.push('SPACE')
    expect(readPendingHumanReview(directorQuery)).toEqual(before)
  })

  it('isolates simultaneous subjects, media and director tasks, then removes only one entry', () => {
    const queries: HumanReviewQuery[] = [
      imageQuery,
      { ...imageQuery, subjectId: 'image-2' },
      { subjectType: 'VIDEO_VARIANT', subjectId: imageQuery.subjectId },
      directorQuery,
      { ...directorQuery, taskId: 'director-2' },
    ]
    queries.forEach((query, index) => {
      expect(persistPendingHumanReview(query, input({
        ...query, reviewKey: `review-${index}`, verdict: 'PASS', reasonCodes: [],
      }))).toBe(true)
    })
    queries.forEach((query, index) => {
      expect(readPendingHumanReview(query)?.reviewKey).toBe(`review-${index}`)
    })
    expect(readPendingHumanReview({ ...imageQuery, subjectId: 'unknown' })).toBeNull()
    expect(persistPendingHumanReview(directorQuery, null)).toBe(true)
    expect(readPendingHumanReview(directorQuery)).toBeNull()
    expect(readPendingHumanReview(queries[4])?.reviewKey).toBe('review-4')
    expect(readPendingHumanReview(imageQuery)?.reviewKey).toBe('review-0')
  })

  it.each([
    { subjectType: 'VIDEO_VARIANT' },
    { subjectId: 'image-2' },
    { taskId: 'different-task' },
  ])('rejects a cross-subject envelope stored under the current key: %j', (overrides) => {
    storeEnvelope({
      schemaVersion: 'human-review-pending.v1', input: { ...input(), ...overrides },
    })
    expect(readPendingHumanReview(imageQuery)).toBeNull()
  })

  it('does not replace an unknown submission when saving a retry fails', () => {
    const pending = input()
    expect(persistPendingHumanReview(imageQuery, pending)).toBe(true)
    vi.spyOn(sessionStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('storage full', 'QuotaExceededError')
    })
    expect(persistPendingHumanReview(imageQuery, input({ reviewKey: 'different-review' })))
      .toBe(false)
    expect(readPendingHumanReview(imageQuery)).toEqual(pending)
  })

  it.each(['{', 'null', '[]', '""', '{}', '{"schemaVersion":"human-review-pending.v2"}'])(
    'ignores damaged or unsupported stored JSON: %s', (raw) => {
      storeRaw(raw)
      expect(() => readPendingHumanReview(imageQuery)).not.toThrow()
      expect(readPendingHumanReview(imageQuery)).toBeNull()
    },
  )

  it.each([
    { reviewKey: '' }, { reviewKey: 42 }, { reasonCodes: 'GARMENT' },
    { reasonCodes: [null] }, { note: null }, { verdict: 'QUALIFIED' },
    { expectedOutputHash: null }, { expectedOutputHash: 'invalid' },
    { verdict: 'PASS', reasonCodes: ['GARMENT'] },
    { reasonCodes: ['OTHER'], note: ' ' },
    { note: 'x'.repeat(256) },
  ])('rejects an invalid pending input: %j', (overrides) => {
    storeEnvelope({
      schemaVersion: 'human-review-pending.v1', input: { ...input(), ...overrides },
    })
    expect(readPendingHumanReview(imageQuery)).toBeNull()
  })

  it('rejects a JSON array masquerading as an output hash instead of coercing it', () => {
    storeEnvelope({
      schemaVersion: 'human-review-pending.v1',
      input: { ...input(), expectedOutputHash: [outputHash] },
    })
    expect(readPendingHumanReview(imageQuery)).toBeNull()
  })

  it('rejects a damaged pending video REWORK and a director entry without its task', () => {
    const videoQuery: HumanReviewQuery = { subjectType: 'VIDEO_VARIANT', subjectId: 'video-1' }
    expect(persistPendingHumanReview(videoQuery, input({
      ...videoQuery, verdict: 'REWORK', reasonCodes: ['MOTION'],
    }))).toBe(true)
    expect(readPendingHumanReview(videoQuery)).toBeNull()
    const missingTaskQuery: HumanReviewQuery = {
      subjectType: 'DIRECTOR_CANDIDATE', subjectId: 'candidate-1',
    }
    expect(persistPendingHumanReview(missingTaskQuery, input(missingTaskQuery))).toBe(true)
    expect(readPendingHumanReview(missingTaskQuery)).toBeNull()
  })
})

describe('pending storage failures', () => {
  it('returns null for an inaccessible read without throwing', () => {
    vi.spyOn(sessionStorage, 'getItem').mockImplementation(() => {
      throw new DOMException('storage blocked', 'SecurityError')
    })
    expect(readPendingHumanReview(imageQuery)).toBeNull()
  })

  it('returns false when a new pending submission cannot be persisted', () => {
    vi.spyOn(sessionStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('storage full', 'QuotaExceededError')
    })
    expect(persistPendingHumanReview(imageQuery, input())).toBe(false)
    expect(readPendingHumanReview(imageQuery)).toBeNull()
  })

  it('reports failed removal and retains evidence for a later recovery', () => {
    expect(persistPendingHumanReview(imageQuery, input())).toBe(true)
    vi.spyOn(sessionStorage, 'removeItem').mockImplementation(() => {
      throw new DOMException('storage blocked', 'SecurityError')
    })
    expect(persistPendingHumanReview(imageQuery, null)).toBe(false)
    expect(readPendingHumanReview(imageQuery)).toEqual(input())
  })

  it('degrades safely when session storage is unavailable', () => {
    vi.stubGlobal('sessionStorage', undefined)
    expect(readPendingHumanReview(imageQuery)).toBeNull()
    expect(persistPendingHumanReview(imageQuery, input())).toBe(false)
    expect(persistPendingHumanReview(imageQuery, null)).toBe(false)
  })

  it('returns false for a non-serializable input without replacing a saved request', () => {
    const pending = input()
    expect(persistPendingHumanReview(imageQuery, pending)).toBe(true)
    const cyclic = { ...pending, reasonCodes: [...pending.reasonCodes] }
    Object.assign(cyclic, { unexpectedCycle: cyclic })
    expect(persistPendingHumanReview(imageQuery, cyclic)).toBe(false)
    expect(readPendingHumanReview(imageQuery)).toEqual(pending)
  })
})
