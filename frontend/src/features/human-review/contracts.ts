export type HumanReviewSubjectType = 'IMAGE_OUTPUT' | 'VIDEO_VARIANT' | 'DIRECTOR_CANDIDATE'
export type HumanReviewVerdict = 'PASS' | 'REWORK' | 'FAIL'
export type HumanReviewReason = 'FACE' | 'GARMENT' | 'REALISM' | 'SPACE' | 'LIGHTING' | 'MOTION' | 'DEFORMATION' | 'CAMERA' | 'OTHER'

export interface HumanReviewQuery {
  subjectType: HumanReviewSubjectType
  subjectId: string
  taskId?: string
}

export interface HumanReviewInput extends HumanReviewQuery {
  reviewKey: string
  expectedOutputHash: string
  verdict: HumanReviewVerdict
  reasonCodes: HumanReviewReason[]
  note: string
}

export interface HumanReviewSubject extends HumanReviewQuery {
  outputHash: string | null
  synthetic: boolean
  packageId?: string | null
  packageRevision?: number | null
}

export interface HumanReviewRecord {
  id: string
  reviewKey: string
  verdict: HumanReviewVerdict
  reasonCodes: HumanReviewReason[]
  note: string | null
  reviewerId: string
  reviewedAt: string
  subject: HumanReviewSubject
}

export interface HumanReviewHistory {
  subject: HumanReviewSubject
  reviews: HumanReviewRecord[]
}

export interface HumanReviewExport {
  schemaVersion: string
  records: HumanReviewRecord[]
  excludedSyntheticCount: number
}
