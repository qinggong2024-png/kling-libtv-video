export type StatusTone = 'neutral' | 'success' | 'warning' | 'danger' | 'active'
export type VariantKind = 'STABLE' | 'DYNAMIC'
export type FeedbackValue = 'LIKE' | 'DISLIKE'
export type FeedbackReason =
  | 'GARMENT_ACCURATE'
  | 'PRODUCT_CLEAR'
  | 'NATURAL_MOTION'
  | 'COMFORTABLE_CAMERA'
  | 'GOOD_PACING'
  | 'STRONG_APPEAL'
  | 'GARMENT_DISTORTED'
  | 'COLOR_INACCURATE'
  | 'LOGO_TEXT_INCORRECT'
  | 'FACE_HAND_ARTIFACT'
  | 'STIFF_MOTION'
  | 'CAMERA_TOO_FAST'
  | 'CHAOTIC_EDITING'
  | 'PRODUCT_UNCLEAR'

export interface Asset {
  id: string
  order: number
  required: boolean
  originalFilename: string
  sha256: string
  width: number
  height: number
  thumbnailUrl: string
  role?: 'STORYBOARD' | 'PRODUCT' | string
  usedForAnalysis?: boolean
  usedForGeneration?: boolean
}

export interface Variant {
  id: string
  kind: VariantKind
  revision: number
  promptText: string
  promptHash: string | null
  generationStatus: string
  downloadStatus: string
  validationStatus: string
  downloadArtifactId: string | null
  errorCode: string | null
  feedback: FeedbackValue | null
  feedbackReasons: FeedbackReason[]
  feedbackComment: string | null
}

export interface Task {
  id: string
  userId: string
  clientTaskId: string
  title: string
  assetCount: number
  userRequirement: string
  analysisModel: string
  generationProvider: string
  phase: string
  phaseReasonCode: string | null
  consistencyLevel: string | null
  analysisResult: Record<string, unknown> | null
  analysisRunId: string | null
  analysisStage: string | null
  analysisStartedAt: string | null
  analysisHeartbeatAt: string | null
  canvasProjectUuid: string | null
  stateVersion: number
  assets: Asset[]
  variants: Variant[]
  pointsQuota: {
    dailyLimit: number
    consumed: number
    reserved: number
    uncertain: number
    remaining: number
  }
  actionCapabilities: {
    canEdit: boolean
    canConfirm: boolean
    canCancel: boolean
    canRetryAnalysis: boolean
    canRegenerate: boolean
    canDownload: boolean
  }
  timing?: {
    stages: Array<{
      key: 'SOURCE_UPLOAD' | 'ANALYSIS' | 'CONFIRMATION' | 'MATERIALIZATION' | 'GENERATION' | 'DOWNLOAD'
      status: 'COMPLETED' | 'ACTIVE' | 'PENDING' | 'FAILED'
      durationSeconds: number | null
      activeStartedAt: string | null
      attemptCount: number | null
    }>
  }
  createdAt: string
  updatedAt: string
}

export interface PromptAssistantResponse {
  task: Task
  advice: string
}

export interface BatchConfirmationResponse {
  results: Array<{
    taskId: string
    status: 'SUCCEEDED' | 'FAILED'
    task: Task | null
    errorCode: string | null
    message: string | null
  }>
  succeededCount: number
  failedCount: number
}

export interface AuthUser {
  userId: string
  username: string
  role: 'ADMIN' | 'OPERATOR' | 'USER'
}

export interface AdminUser {
  id: string
  username: string
  role: 'ADMIN' | 'OPERATOR' | 'USER'
  isActive: boolean
  createdAt: string
}

export interface UploadResult {
  id: string
  originalFilename: string
  sha256: string
  width: number
  height: number
  mimeType: string
  thumbnailUrl: string
}

export interface SystemStatus {
  environment: string
  libtvAdapter: string
  aiAdapter: string
  openaiModel: string
  openaiConfigured: boolean
  libtvConfigured: boolean
  outputRetentionDays: number
  downloadConcurrency: number
  technicalValidationConcurrency: number
  zipEnabled: boolean
  phaseOneUserId: string | null
  phaseOneAdminId: string | null
  sharedAuthentication: boolean
  csrfCookieName: string
  kling: {
    enabled: boolean
    status: string
    available: boolean
    authenticated: boolean
    reason: string | null
    cliVersion: string | null
    models: string[]
    supportsMultipleImages: boolean
    imageInputLimit: number
    fallbackMode: 'disabled' | 'first_last_frame'
  }
}

export interface KlingStatus {
  enabled: boolean
  status: string
  available: boolean
  authenticated: boolean
  reason: string | null
  cliVersion: string | null
  checkedAt: string | null
  supportedModels: string[]
  supportedTools: string[]
  videoDurations: string[]
  aspectRatios: string[]
  imageInputLimit: number
  supportsTailImage: boolean
  supportsMultipleImages: boolean
  supportsWatermarkFreeOutput: boolean
}

export interface AdminCredentialsStatus {
  libtvConfigured: boolean
  modelConfigured: boolean
  modelBaseUrl: string | null
  updatedAt: string | null
}

export interface LibTVAccount {
  accountId: string
  accountName: string
  accountType: string
  isActive: boolean
  teamId: string | number | null
}

export interface LibTVAccountStatus {
  available: boolean
  authenticated: boolean
  loginInProgress: boolean
  activeAccount: LibTVAccount | null
  accounts: LibTVAccount[]
}

export interface LibTVLoginStart {
  sessionId: string
  loginUrl: string
  startedAt: string
  alreadyRunning: boolean
}

export interface LibTVAccountSwitch {
  ok: boolean
  accountId: string
  accountName: string
  accountType: string
  teamId: string | number | null
  alreadyActive: boolean
}

export interface Reconciliation {
  attemptId: string
  projectUuid: string
  nodeKey: string
  taskId: string | null
  status: string
  chargeStatus: string
  errorCode: string | null
  updatedAt: string
}

export interface OperationsSnapshot {
  runtime: {
    version: number
    config: {
      globalPaused: boolean
      paidSubmissionsPaused: boolean
      libtvAuthRequired?: boolean
      promptConfirmationRequired?: boolean
      generationConcurrency: { sameProject: number; perUser: number; global: number }
      preparedQueue: { lowWatermark: number; highWatermark: number }
      autoConfirmLevels: string[]
    }
  }
  queues: { prepared: number; generation: number; running: number; unknown: number }
  metrics: {
    duplicateGenerationTotal: number
    crossTaskConnectionTotal: number
    unknownAfterSubmitRate: number
    generationSlotUtilization: number
    runnerActiveCommandHosts: number
    runnerOrphanProcesses: number
    pointsReserved: number
    pointsConsumed: number
    pointsUncertain: number
  }
  pipelinePerformance: {
    windowDays: number
    stages: Record<string, {
      sampleCount: number
      p50Seconds: number | null
      p95Seconds: number | null
    }>
    automationBottleneck: string | null
    currentConstraint: string
    throughput: {
      completedVideos24h: number
      completedTasks24h: number
    }
    backlog: {
      analysis: number
      confirmation: number
      materialization: number
      queued: number
      generation: number
      delivery: number
    }
  }
  runners: Array<{ id: string; hostname: string; status: string; freeDiskPercent: number; lastHeartbeatAt: string }>
  canvases: Array<{ projectUuid: string; userId: string; mutationState: string; executionState: string; preparedVideos: number }>
  points: Record<string, number>
  alerts: Array<{ severity: string; code: string; action: string }>
}

export type RuntimeConfigSnapshot = OperationsSnapshot['runtime'] & {
  reason: string
  createdAt: string | null
}
