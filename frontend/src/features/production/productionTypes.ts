// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { fetchImageAssetFile } from '../../api'
import { type Task, type VariantKind } from '../../types'
import { type ImageCenterVideoHandoff } from '../image-center/ImageCenter'
import { type SubjectReferenceFiles } from '../../subjectFiles'

export type UploadBucket = 'storyboard' | 'product'
export type Material = { id: string; file: File; sourceImageOutputId?: string }
export type RemixSeed = { id: string; storyboards: File[]; storyboardOutputIds?: string[]; products: File[]; subjectFiles?: SubjectReferenceFiles; requirement?: string }
export const UPLOAD_CONCURRENCY = 4
export function taskPrompt(task: Task, kind: VariantKind): string {
  return task.variants.find((variant) => variant.kind === kind)?.promptText
    ?? task.variants[0]?.promptText
    ?? ''
}

export async function imageCenterOutputFile(
  output: ImageCenterVideoHandoff['outputs'][number],
  outfitName: string,
  index: number,
): Promise<File> {
  if (output.file) return output.file
  if (!output.url) throw new Error(`“${outfitName}”的分镜 ${index + 1} 暂无可用图片文件。`)
  return fetchImageAssetFile(output.url, `${outfitName}-分镜-${index + 1}`)
}

export type PlanShot = {
  entryState?: string
  action?: string
  exitState?: string
  camera?: string
  productDisplay?: string
  shotFunction?: string
  durationWeight?: number
}
export type VariantPlan = { continuityStrategy?: string; shots?: PlanShot[] }
export type AnalysisResult = {
  garmentFacts?: { category?: string; mainColor?: string; secondaryColor?: string; print?: string; logo?: string; text?: string; fit?: string; frontSellingPoints?: string[]; backSellingPoints?: string[] }
  storyboardFacts?: Array<{ scene?: string; framing?: string; pose?: string; actionCandidates?: string[] }>
  consistencyObservations?: { summary?: string }
  riskFlags?: string[]
  stablePlan?: VariantPlan
  dynamicPlan?: VariantPlan
}
