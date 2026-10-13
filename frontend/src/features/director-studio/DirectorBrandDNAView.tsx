import type { SiteStyleProfileSummary } from '../../types'
import type { BrandDNASnapshot } from './directorBrandDNA'

export function DirectorBrandDNAView({ profile, snapshot }: { profile?: SiteStyleProfileSummary | null; snapshot?: BrandDNASnapshot }) {
  if (!profile && !snapshot) return null
  const fields = snapshot ? [
    ['受众', snapshot.audience],
    ['视觉', [snapshot.visualDNA.tone, ...snapshot.visualDNA.palette].join(' · ')],
    ['人物风格', snapshot.characterDNA.expressionLanguage],
    ['场景', snapshot.sceneDNA.preferredEnvironment.join(' · ')],
    ['镜头', snapshot.cameraDNA.language],
    ['避免', [...snapshot.avoid.mismatches, ...snapshot.avoid.motion].join(' · ')],
  ] : [
    ['受众', profile!.audience],
    ['视觉', [profile!.tone, ...profile!.palette].join(' · ')],
    ['人物风格', profile!.expressionLanguage],
    ['场景', profile!.preferredEnvironment?.join(' · ')],
    ['镜头', profile!.cameraLanguage],
    ['避免', [...profile!.forbiddenMismatches, ...(profile!.forbiddenMotion ?? [])].join(' · ')],
  ]
  return <details className="director-evidence" aria-label="Brand Creative DNA">
    <summary>Brand DNA · {snapshot?.name ?? profile?.name} · {snapshot?.profileVersion ?? profile?.version}</summary>
    <p className="director-evidence__note">{snapshot ? '任务已绑定的目录快照' : '目录建议 · 尚未绑定任务'}</p>
    <dl className="director-evidence-list">
      {fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || '未提供'}</dd></div>)}
      <div><dt>目录 ID</dt><dd>{snapshot?.profileId ?? profile?.id}</dd></div>
    </dl>
  </details>
}
