import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { SiteStyleProfileSummary } from '../../types'
import { DirectorBrandDNAView } from './DirectorBrandDNAView'
import { selectDirectorBrandProfile } from './directorBrandDNA'

const profile: SiteStyleProfileSummary = {
  id: 'brand-one', name: 'Same name', version: '1.0.0', libraryScope: 'brand', status: 'active',
  tone: 'dark street', audience: 'Configured audience', palette: ['black', 'red'],
  expressionLanguage: 'natural expression', preferredEnvironment: ['bedroom mirror'],
  cameraLanguage: 'eye level', forbiddenMismatches: ['AI beauty'], forbiddenMotion: [],
  siteUrl: '', sourceUrls: [], retrievedAt: '', evidenceLevel: 'restricted_site',
  typography: '', openingRule: '', middleRule: '', endingRule: '', preferredShots: [],
  preferredActions: [], pacing: '', productPriorities: [], researchNote: '',
  motionEnergy: 'standard', primaryMotionPool: [], microMotionPool: [], expressionPool: [],
  cameraPool: [], productRiskRules: [], dedupeRecentCount: 5, dedupeComboWindow: 8,
  dedupeFamilyWindow: 10, dedupeFamilyLimit: 3, brandId: 'brand-one',
}

describe('Brand DNA selection and read preview', () => {
  it('uses stable ID and refuses ambiguous names or retired profiles', () => {
    const duplicate = { ...profile, id: 'brand-two' }
    expect(selectDirectorBrandProfile([profile, duplicate], 'brand-two', profile.name)).toBe(duplicate)
    expect(selectDirectorBrandProfile([profile, duplicate], '', profile.name)).toBeNull()
    expect(selectDirectorBrandProfile([profile], 'missing', profile.name)).toBeNull()
    expect(selectDirectorBrandProfile([{ ...profile, status: 'retired' }], profile.id, profile.name)).toBeNull()
    expect(selectDirectorBrandProfile([profile], '', profile.name)).toBe(profile)
  })

  it('shows sourced configuration as suggestions before task binding', () => {
    const markup = renderToStaticMarkup(<DirectorBrandDNAView profile={profile} />)
    expect(markup).toContain('目录建议 · 尚未绑定任务')
    expect(markup).toContain('brand-one')
    expect(markup).toContain('Configured audience')
    expect(markup).toContain('AI beauty')
    expect(renderToStaticMarkup(<DirectorBrandDNAView />)).toBe('')
  })
})
