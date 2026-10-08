// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import {Activity, AlertTriangle, Check, ChevronRight, Clapperboard, Copy, Globe2, LoaderCircle, LockKeyhole, Package, Pencil, Plus, Search, ShieldCheck, UserRound, WandSparkles} from 'lucide-react'
import {useDeferredValue, useEffect, useMemo, useState} from 'react'
import {getMotionActions, getSiteStyleProfiles, getVideoTemplates} from '../../api'
import {type MotionActionSummary, type SiteStyleProfileSummary, type VideoTemplateSummary} from '../../types'
import {KlingSubjectsLibrary} from '../../KlingSubjectsLibrary'
import {CatalogEditor} from '../../CatalogEditor'
import {copyText} from '../../shared/utils/copyText'
import {DataFreshness} from '../../shared/components/DataFreshness'
import {type ActionCategoryFilter, type ContentLibraryKind, type ContentLibraryScope, ACTION_CATEGORY_LABELS, styleStatus} from './libraryTypes'
import {EmptyState} from '../../shared/components/Section'

export function ContentLibraryView({ actorId, canDeleteSubjects, canEditCatalog }: {
  actorId: string | null
  canDeleteSubjects: boolean
  canEditCatalog: boolean
}) {
  const [scope, setScope] = useState<ContentLibraryScope>('general')
  const [kind, setKind] = useState<ContentLibraryKind>('actions')
  const tab = scope === 'subjects' ? 'subjects' : kind
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query.trim().toLowerCase())
  const [category, setCategory] = useState<ActionCategoryFilter>('all')
  const [brandFilter, setBrandFilter] = useState('all')
  const [actions, setActions] = useState<MotionActionSummary[]>([])
  const [profiles, setProfiles] = useState<SiteStyleProfileSummary[]>([])
  const [templates, setTemplates] = useState<VideoTemplateSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastSyncedAt, setLastSyncedAt] = useState<number | null>(null)
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false)
  const [copiedActionId, setCopiedActionId] = useState('')
  // 复制失败单独存放：本组件的 error 会连带隐藏整个内容库列表，不适合承载这类瞬时提示。
  const [copyActionError, setCopyActionError] = useState('')
  const [editor, setEditor] = useState<
    | { kind: 'action'; item?: MotionActionSummary; initialScope?: 'general' | 'brand' }
    | { kind: 'style'; item?: SiteStyleProfileSummary; initialScope?: 'general' | 'brand' }
    | null
  >(null)

  useEffect(() => {
    let active = true
    Promise.all([getMotionActions(), getSiteStyleProfiles(), getVideoTemplates()])
      .then(([nextActions, nextProfiles, nextTemplates]) => {
        if (!active) return
        setActions(nextActions)
        setProfiles(nextProfiles)
        setTemplates(nextTemplates)
        setLastSyncedAt(Date.now())
        setHasLoadedOnce(true)
        setError('')
      })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : '内容库加载失败')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const templateNames = useMemo(
    () => new Map(templates.map((template) => [template.id, template.name])),
    [templates],
  )
  const actionNames = useMemo(
    () => new Map(actions.map((action) => [action.id, action.label])),
    [actions],
  )
  const visibleActions = useMemo(() => actions.filter((action) => {
    if (action.libraryScope !== scope) return false
    if (scope === 'brand' && brandFilter !== 'all' && action.brandId !== brandFilter) return false
    if (category !== 'all' && action.category !== category) return false
    if (!deferredQuery) return true
    return [
      action.label,
      action.id,
      action.instruction,
      action.purpose,
      ACTION_CATEGORY_LABELS[action.category],
      ...action.requirements,
      ...action.avoid,
    ].join(' ').toLowerCase().includes(deferredQuery)
  }), [actions, brandFilter, category, deferredQuery, scope])
  const visibleProfiles = useMemo(() => profiles.filter((profile) => {
    if (profile.libraryScope !== scope) return false
    if (scope === 'brand' && brandFilter !== 'all' && profile.brandId !== brandFilter) return false
    if (!deferredQuery) return true
    return [
      profile.name,
      profile.tone,
      profile.expressionLanguage,
      profile.audience,
      profile.cameraLanguage,
      profile.openingRule,
      profile.middleRule,
      profile.endingRule,
      ...profile.preferredShots,
      ...profile.productPriorities,
      ...profile.preferredActions.map((id) => actionNames.get(id) ?? id),
      ...profile.primaryMotionPool.map((id) => actionNames.get(id) ?? id),
      ...profile.microMotionPool.map((id) => actionNames.get(id) ?? id),
      profile.motionEnergy,
    ].join(' ').toLowerCase().includes(deferredQuery)
  }), [actionNames, brandFilter, deferredQuery, profiles, scope])
  const generalActionCount = actions.filter((action) => action.libraryScope === 'general').length
  const generalStyleCount = profiles.filter((profile) => profile.libraryScope === 'general').length
  const brandActionCount = actions.filter((action) => action.libraryScope === 'brand').length
  const brandStyleCount = profiles.filter((profile) => profile.libraryScope === 'brand').length
  const brandNames = useMemo(
    () => new Map(profiles.filter((profile) => profile.libraryScope === 'brand').map((profile) => [profile.id, profile.name])),
    [profiles],
  )
  const hasActiveLibraryFilters = Boolean(deferredQuery)
    || (scope === 'brand' && brandFilter !== 'all')
    || (tab === 'actions' && category !== 'all')

  const clearLibraryFilters = () => {
    setQuery('')
    setBrandFilter('all')
    setCategory('all')
  }

  function moveTab<T extends string>(event: React.KeyboardEvent<HTMLButtonElement>, values: T[], current: T, select: (value: T) => void) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const index = values.indexOf(current)
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? values.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + values.length) % values.length
    select(values[nextIndex])
    requestAnimationFrame(() => document.getElementById(`${values[nextIndex]}-tab`)?.focus())
  }

  const copyAction = async (action: MotionActionSummary) => {
    // 必须走 copyText：局域网 IP + HTTP 属于非安全上下文，此时 navigator.clipboard 不存在，
    // 直接调用会抛 TypeError，复制功能整条不可用。copyText 内部会退化为 execCommand 方案。
    try {
      await copyText(action.instruction)
      setCopyActionError('')
      setCopiedActionId(action.id)
      window.setTimeout(() => setCopiedActionId(''), 1800)
    } catch (cause) {
      setCopyActionError(cause instanceof Error ? cause.message : '复制失败，请手动选中提示词后复制')
    }
  }

  const catalogSaved = (
    item: MotionActionSummary | SiteStyleProfileSummary,
    kind: 'action' | 'style',
  ) => {
    if (kind === 'action') {
      const saved = item as MotionActionSummary
      setActions((current) => current.some((action) => action.id === saved.id)
        ? current.map((action) => action.id === saved.id ? saved : action)
        : [...current, saved])
    } else {
      const saved = item as SiteStyleProfileSummary
      if (saved.status === 'retired') {
        setProfiles((current) => current.filter((profile) => profile.id !== saved.id))
        setEditor(null)
        return
      }
      setProfiles((current) => current.some((profile) => profile.id === saved.id)
        ? current.map((profile) => profile.id === saved.id ? saved : profile)
        : [...current, saved])
    }
    setEditor(null)
  }

  return <div className="page-view content-library-view">
    <div className="page-title content-library-title">
      <div><span>生产素材库</span><h1>内容与主体库</h1><p>通用资产可跨品牌复用，品牌专属资产只服务对应品牌。</p><DataFreshness timestamp={lastSyncedAt} stale={Boolean(error && hasLoadedOnce)} /></div>
      {tab !== 'subjects' ? <label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={tab === 'actions' ? '搜索动作、用途或风险' : '搜索风格、语气或镜头'} aria-label={tab === 'actions' ? '搜索动作库' : '搜索风格库'} />{query ? <button type="button" className="search-field-clear" onClick={(event) => { event.preventDefault(); setQuery('') }} aria-label="清除内容库搜索关键词" title="清除搜索"><span aria-hidden="true">×</span></button> : null}</label> : null}
    </div>

    <section className="library-overview" aria-label="内容库概览">
      <div><span className="library-overview-icon library-overview-icon--blue"><Activity size={20} /></span><span><small>通用动作</small><strong>{generalActionCount}</strong><em>跨品牌复用</em></span></div>
      <div><span className="library-overview-icon library-overview-icon--green"><Clapperboard size={20} /></span><span><small>通用风格</small><strong>{generalStyleCount}</strong><em>不绑定品牌</em></span></div>
      <div><span className="library-overview-icon library-overview-icon--violet"><LockKeyhole size={20} /></span><span><small>品牌风格</small><strong>{brandStyleCount}</strong><em>独立版本与证据</em></span></div>
      <div><span className="library-overview-icon library-overview-icon--orange"><WandSparkles size={20} /></span><span><small>品牌动作</small><strong>{brandActionCount}</strong><em>仅限所属品牌</em></span></div>
    </section>

    <div className="library-scope-tabs" role="tablist" aria-label="内容库归属">
      <button id="general-tab" type="button" role="tab" tabIndex={scope === 'general' ? 0 : -1} aria-selected={scope === 'general'} aria-controls="general-panel" className={scope === 'general' ? 'is-active' : ''} onKeyDown={(event) => moveTab(event, ['general', 'brand', 'subjects'], scope, setScope)} onClick={() => { setScope('general'); setBrandFilter('all') }}><Globe2 size={18} /><span><strong>通用内容</strong><small>所有品牌可复用</small></span></button>
      <button id="brand-tab" type="button" role="tab" tabIndex={scope === 'brand' ? 0 : -1} aria-selected={scope === 'brand'} aria-controls="brand-panel" className={scope === 'brand' ? 'is-active' : ''} onKeyDown={(event) => moveTab(event, ['general', 'brand', 'subjects'], scope, setScope)} onClick={() => setScope('brand')}><LockKeyhole size={18} /><span><strong>品牌专属</strong><small>按品牌隔离使用</small></span></button>
      <button id="subjects-tab" type="button" role="tab" tabIndex={scope === 'subjects' ? 0 : -1} aria-selected={scope === 'subjects'} aria-controls="subjects-panel" className={scope === 'subjects' ? 'is-active' : ''} onKeyDown={(event) => moveTab(event, ['general', 'brand', 'subjects'], scope, setScope)} onClick={() => setScope('subjects')}><Package size={18} /><span><strong>历史主体</strong><small>视频主体资产</small></span></button>
    </div>

    {scope !== 'subjects' ? <div id={`${scope}-panel`} role="tabpanel" aria-labelledby={`${scope}-tab`} className="library-toolbar">
      <div className="library-tabs" role="tablist" aria-label={`${scope === 'general' ? '通用' : '品牌专属'}内容类型`}>
        <button id="actions-tab" type="button" role="tab" tabIndex={kind === 'actions' ? 0 : -1} aria-selected={kind === 'actions'} aria-controls="actions-panel" className={kind === 'actions' ? 'is-active' : ''} onKeyDown={(event) => moveTab(event, ['actions', 'styles'], kind, setKind)} onClick={() => setKind('actions')}><Activity size={17} />动作库<span>{scope === 'general' ? generalActionCount : brandActionCount}</span></button>
        <button id="styles-tab" type="button" role="tab" tabIndex={kind === 'styles' ? 0 : -1} aria-selected={kind === 'styles'} aria-controls="styles-panel" className={kind === 'styles' ? 'is-active' : ''} onKeyDown={(event) => moveTab(event, ['actions', 'styles'], kind, setKind)} onClick={() => setKind('styles')}><Clapperboard size={17} />风格库<span>{scope === 'general' ? generalStyleCount : brandStyleCount}</span></button>
      </div>
      <div className="library-toolbar-actions">
        {scope === 'brand' ? <label className="library-filter"><span>品牌</span><select value={brandFilter} onChange={(event) => setBrandFilter(event.target.value)}><option value="all">全部品牌</option>{[...brandNames].map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label> : null}
        {tab === 'actions' ? <label className="library-filter"><span>分类</span><select value={category} onChange={(event) => setCategory(event.target.value as ActionCategoryFilter)}><option value="all">全部分类</option>{Object.entries(ACTION_CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label> : <span className="library-safety-note"><ShieldCheck size={16} />草稿风格不会自动进入付费生产</span>}
        {canEditCatalog ? <button type="button" className="primary-button library-add-button" onClick={() => setEditor({ kind: tab === 'actions' ? 'action' : 'style', initialScope: scope })}><Plus size={16} />新增{scope === 'brand' ? '品牌' : '通用'}{tab === 'actions' ? '动作' : '风格'}</button> : null}
      </div>
    </div> : null}

    {tab !== 'subjects' && hasActiveLibraryFilters ? <div className="filter-notice library-filter-notice" role="status"><Search size={15} /><span>当前筛选匹配 {tab === 'actions' ? visibleActions.length : visibleProfiles.length} 条内容。</span><button type="button" className="text-button" onClick={clearLibraryFilters}>清除筛选</button></div> : null}

    {tab !== 'subjects' && loading && !hasLoadedOnce ? <div id={`${tab}-panel`} role="tabpanel" aria-labelledby={`${tab}-tab`} /> : null}
    {tab !== 'subjects' && loading ? <div className="library-loading" role="status"><LoaderCircle className="spin" size={22} /><span>正在读取内容库</span></div> : null}
    {tab !== 'subjects' && error ? <div className="inline-alert inline-alert--danger library-error" role="alert"><AlertTriangle size={17} /><span>{hasLoadedOnce ? `${error}，已保留上次成功读取的内容。` : error}</span></div> : null}
    {copyActionError ? <div className="inline-alert inline-alert--danger library-error" role="alert"><AlertTriangle size={17} /><span>{copyActionError}</span></div> : null}

    {!loading && hasLoadedOnce && tab === 'actions' ? <section id="actions-panel" role="tabpanel" aria-labelledby="actions-tab" className="action-library-grid" aria-label="动作提示词列表">
      {visibleActions.map((action) => <article className="action-library-card" key={action.id}>
        <header>
          <div className="library-card-labels"><span className={`action-category action-category--${action.category}`}>{ACTION_CATEGORY_LABELS[action.category]}</span>{action.brandId ? <span className="library-brand-label"><LockKeyhole size={11} />{brandNames.get(action.brandId) ?? action.brandId}</span> : null}</div>
          <span className={action.riskLevel === 'conditional' ? 'library-status library-status--warning' : 'library-status'}>{action.riskLevel === 'conditional' ? '需满足前提' : '低风险'}</span>
        </header>
        <div className="action-card-title"><div><h2>{action.label}</h2><code>{action.id}</code></div><span className="library-card-actions">{canEditCatalog ? <button type="button" className="icon-button" onClick={() => setEditor({ kind: 'action', item: action })} aria-label={`编辑${action.label}`} title="编辑动作"><Pencil size={16} /></button> : null}<button type="button" className="icon-button" onClick={() => void copyAction(action)} aria-label={`复制${action.label}提示词`} title="复制提示词">{copiedActionId === action.id ? <Check size={17} /> : <Copy size={17} />}</button></span></div>
        {action.baseActionId ? <p className="library-inheritance"><ChevronRight size={14} />基于通用动作：{actionNames.get(action.baseActionId) ?? action.baseActionId}</p> : null}
        <p className="action-instruction">{action.instruction}</p>
        <div className="action-purpose"><span>商品目的</span><p>{action.purpose}</p></div>
        <div className="library-chip-group"><span>适用模板</span><div>{action.compatibleTemplates.map((id) => <i key={id}>{templateNames.get(id) ?? id}</i>)}</div></div>
        {action.requirements.length || action.avoid.length ? <details className="library-details"><summary>使用前提与避坑<ChevronRight size={16} /></summary><div>{action.requirements.length ? <section><strong>使用前提</strong><ul>{action.requirements.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}{action.avoid.length ? <section><strong>避免</strong><ul>{action.avoid.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}</div></details> : null}
      </article>)}
    </section> : null}

    {!loading && hasLoadedOnce && tab === 'styles' ? <section id="styles-panel" role="tabpanel" aria-labelledby="styles-tab" className="style-library-grid" aria-label="站点视频风格列表">
      {visibleProfiles.map((profile) => {
        const status = styleStatus(profile)
        return <article className="style-library-card" key={profile.id}>
        <header>
          <div><span className={status.warning ? 'library-status library-status--warning' : 'library-status library-status--verified'}>{status.label}</span><span className="library-version">{profile.version}</span></div>
          {canEditCatalog ? <button type="button" className="secondary-button library-edit-button" onClick={() => setEditor({ kind: 'style', item: profile })}><Pencil size={15} />编辑风格</button> : null}
        </header>
        <div className="style-card-title"><div><h2>{profile.name}</h2><p>{profile.tone}</p></div><span className="style-card-mark"><Clapperboard size={20} /></span></div>
        <div className="style-expression"><span title="人物表达"><UserRound size={15} /></span><p>{profile.expressionLanguage}</p></div>
        <div className="style-grammar">
          <div><span>开</span><p>{profile.openingRule}</p></div>
          <div><span>承</span><p>{profile.middleRule}</p></div>
          <div><span>收</span><p>{profile.endingRule}</p></div>
        </div>
        <div className="style-camera"><span>镜头触感 · 动作能量 {profile.motionEnergy}</span><p>{profile.cameraLanguage}</p><small>{profile.pacing}</small></div>
        <details className="library-details style-library-details"><summary>镜头、动作与商品规则<ChevronRight size={16} /></summary><div>
          <section><strong>适用受众</strong><p>{profile.audience}</p></section>
          <section><strong>视觉语言</strong><p>{profile.typography}</p>{profile.palette.length ? <div className="detail-chip-row">{profile.palette.map((item) => <i key={item}>{item}</i>)}</div> : null}</section>
          <section><strong>优先镜头</strong><div className="detail-chip-row">{profile.preferredShots.map((item) => <i key={item}>{item}</i>)}</div></section>
          <section><strong>关联动作</strong><div className="detail-chip-row">{profile.preferredActions.map((id) => <i key={id}>{actionNames.get(id) ?? id}</i>)}</div></section>
          <section><strong>动作选择器</strong><p>主动作每条选一项，微动作按素材能力补充；最近 {profile.dedupeRecentCount} 条主动作、{profile.dedupeComboWindow} 条动作+镜头组合参与去重。</p><div className="detail-chip-row">{profile.primaryMotionPool.map((id) => <i key={id}>{actionNames.get(id) ?? id}</i>)}</div></section>
          <section><strong>商品重点</strong><ul>{profile.productPriorities.map((item) => <li key={item}>{item}</li>)}</ul></section>
          <section className="style-avoid"><strong>禁止错配</strong><ul>{profile.forbiddenMismatches.map((item) => <li key={item}>{item}</li>)}</ul></section>
          <section className="style-evidence"><strong>研究说明</strong><p>{profile.researchNote}</p><small>复核日期 {profile.retrievedAt} · {profile.sourceUrls.length} 条证据来源</small></section>
        </div></details>
      </article>})}
    </section> : null}

    {tab === 'subjects' ? <div id="subjects-panel" role="tabpanel" aria-labelledby="subjects-tab"><KlingSubjectsLibrary actorId={actorId} canDelete={canDeleteSubjects} /></div> : null}

    {!loading && hasLoadedOnce && ((tab === 'actions' && !visibleActions.length) || (tab === 'styles' && !visibleProfiles.length)) ? <EmptyState icon={scope === 'brand' ? <LockKeyhole size={24} /> : <Search size={24} />} title={hasActiveLibraryFilters ? '没有匹配内容' : `还没有${scope === 'brand' ? '品牌专属' : '通用'}${tab === 'actions' ? '动作' : '风格'}`} description={hasActiveLibraryFilters ? '换一个关键词或清除筛选后再试。' : canEditCatalog ? `使用右上角按钮新增第一条${tab === 'actions' ? '动作' : '风格'}。` : '当前库尚未录入内容。'} action={hasActiveLibraryFilters ? <button type="button" className="secondary-button" onClick={clearLibraryFilters}>清除筛选</button> : undefined} /> : null}
    {editor ? <CatalogEditor target={editor} actions={actions} profiles={profiles} templates={templates} onClose={() => setEditor(null)} onSaved={catalogSaved} /> : null}
  </div>
}
