import type { SiteStyleProfileSummary } from '../../types'

export interface BrandDNASnapshot {
  profileId: string
  profileVersion: string
  name: string
  audience: string | null
  visualDNA: { tone: string; palette: string[] }
  characterDNA: { expressionLanguage: string; expressionPool: string[]; identity: null }
  sceneDNA: { preferredEnvironment: string[] }
  cameraDNA: { language: string; pool: string[]; preferredShots: string[] }
  avoid: { mismatches: string[]; motion: string[] }
  productConstraints: { priorities: string[]; riskRules: string[] }
  contentHash: string
}

export function selectDirectorBrandProfile(profiles: SiteStyleProfileSummary[], profileId: string, legacyName: string): SiteStyleProfileSummary | null {
  const eligible = profiles.filter(profile => profile.libraryScope === 'brand' && profile.status === 'active')
  const matches = profileId ? eligible.filter(profile => profile.id === profileId) : eligible.filter(profile => profile.name === legacyName)
  return matches.length === 1 ? matches[0] : null
}
