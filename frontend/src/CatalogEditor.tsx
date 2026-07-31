import { AlertTriangle, CheckCircle2, Lightbulb, LoaderCircle, Save, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { createPortal } from 'react-dom'
import {
  createMotionAction,
  createSiteStyleProfile,
  updateMotionAction,
  updateSiteStyleProfile,
} from './api'
import type {
  MotionActionSummary,
  MotionActionWrite,
  SiteStyleProfileSummary,
  SiteStyleProfileWrite,
  VideoTemplateSummary,
} from './types'

type EditorTarget =
  | { kind: 'action'; item?: MotionActionSummary; initialScope?: 'general' | 'brand' }
  | { kind: 'style'; item?: SiteStyleProfileSummary; initialScope?: 'general' | 'brand' }

type Props = {
  target: EditorTarget
  actions: MotionActionSummary[]
  profiles: SiteStyleProfileSummary[]
  templates: VideoTemplateSummary[]
  onClose: () => void
  onSaved: (item: MotionActionSummary | SiteStyleProfileSummary, kind: EditorTarget['kind']) => void
}

const today = () => new Date().toISOString().slice(0, 10)
const toLines = (items: string[]) => items.join('\n')
const fromLines = (value: string) => [...new Set(value.split(/\r?\n|；/).map((item) => item.trim()).filter(Boolean))]

function Field({
  label,
  hint,
  wide,
  children,
}: {
  label: string
  hint?: string
  wide?: boolean
  children: React.ReactNode
}) {
  return <label className={`catalog-editor-field${wide ? ' is-wide' : ''}`}>
    <span>{label}</span>
    {children}
    {hint ? <small>{hint}</small> : null}
  </label>
}

function actionInitial(item?: MotionActionSummary, initialScope: 'general' | 'brand' = 'general') {
  return {
    id: item?.id ?? '',
    label: item?.label ?? '',
    category: item?.category ?? 'outfit',
    instruction: item?.instruction ?? '',
    purpose: item?.purpose ?? '',
    compatibleTemplates: item?.compatibleTemplates ?? [],
    requirements: toLines(item?.requirements ?? []),
    avoid: toLines(item?.avoid ?? []),
    riskLevel: item?.riskLevel ?? 'low',
    libraryScope: item?.libraryScope ?? initialScope,
    brandId: item?.brandId ?? '',
    baseActionId: item?.baseActionId ?? '',
  } satisfies Record<string, string | string[]>
}

function styleInitial(item?: SiteStyleProfileSummary, initialScope: 'general' | 'brand' = 'brand') {
  return {
    id: item?.id ?? '',
    status: item?.status ?? 'draft',
    name: item?.name ?? '',
    siteUrl: item?.siteUrl ?? '',
    sourceUrls: toLines(item?.sourceUrls ?? []),
    retrievedAt: item?.retrievedAt ?? today(),
    evidenceLevel: item?.evidenceLevel ?? 'restricted_site',
    tone: item?.tone ?? '',
    expressionLanguage: item?.expressionLanguage ?? '',
    audience: item?.audience ?? '',
    palette: toLines(item?.palette ?? []),
    typography: item?.typography ?? '',
    cameraLanguage: item?.cameraLanguage ?? '',
    openingRule: item?.openingRule ?? '',
    middleRule: item?.middleRule ?? '',
    endingRule: item?.endingRule ?? '',
    preferredShots: toLines(item?.preferredShots ?? []),
    preferredActions: toLines(item?.preferredActions ?? []),
    pacing: item?.pacing ?? '',
    productPriorities: toLines(item?.productPriorities ?? []),
    forbiddenMismatches: toLines(item?.forbiddenMismatches ?? []),
    researchNote: item?.researchNote ?? '',
    libraryScope: item?.libraryScope ?? initialScope,
  }
}

function ActionEditor({
  item,
  initialScope,
  actions,
  profiles,
  templates,
  onClose,
  onSaved,
}: {
  item?: MotionActionSummary
  initialScope?: 'general' | 'brand'
  actions: MotionActionSummary[]
  profiles: SiteStyleProfileSummary[]
  templates: VideoTemplateSummary[]
  onClose: () => void
  onSaved: Props['onSaved']
}) {
  const [draft, setDraft] = useState(() => actionInitial(item, initialScope))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const update = (key: keyof typeof draft, value: string | string[]) => setDraft((current) => ({ ...current, [key]: value }))
  const suggestions = useMemo(() => {
    const next: string[] = []
    if (!/^[a-z][a-z0-9_]*$/.test(draft.id)) next.push('ID 使用英文小写与下划线，例如 sleeve_detail_pause。')
    if (draft.libraryScope === 'general' && draft.instruction.length < 35) next.push('动作指令建议写到 35 字以上，交代起始姿态、动作路径和结束画面。')
    if (draft.libraryScope === 'general' && !/(停|结束|保持|回到)/.test(draft.instruction)) next.push('补充明确的结束状态，避免模型持续运动。')
    if (!/(商品|服装|图案|文字|版型|面料)/.test(draft.instruction)) next.push('说明动作如何保护商品可见性，不要只描述人物表演。')
    if (!draft.compatibleTemplates.length) next.push('至少选择一个可兼容的视频模板。')
    if (draft.riskLevel === 'conditional' && !draft.requirements.trim()) next.push('条件动作必须写清输入画面需要满足的前提。')
    if (draft.libraryScope === 'brand' && !draft.brandId) next.push('品牌专属动作必须选择所属品牌。')
    if (draft.libraryScope === 'brand' && !draft.baseActionId) next.push('品牌专属动作必须选择一个通用基础动作，只记录风格差异。')
    return next
  }, [draft])

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const payload: MotionActionWrite = {
        id: draft.id.trim(),
        label: draft.label.trim(),
        category: draft.category as MotionActionWrite['category'],
        instruction: draft.instruction.trim(),
        purpose: draft.purpose.trim(),
        compatibleTemplates: draft.compatibleTemplates,
        requirements: fromLines(draft.requirements),
        avoid: fromLines(draft.avoid),
        riskLevel: draft.riskLevel as MotionActionWrite['riskLevel'],
        libraryScope: draft.libraryScope as MotionActionWrite['libraryScope'],
        brandId: draft.libraryScope === 'brand' ? draft.brandId : null,
        baseActionId: draft.libraryScope === 'brand' ? draft.baseActionId : null,
      }
      const saved = item
        ? await updateMotionAction(item.id, payload)
        : await createMotionAction(payload)
      onSaved(saved, 'action')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '动作提示词保存失败')
    } finally {
      setBusy(false)
    }
  }

  return <form className="catalog-editor-form" onSubmit={(event) => void save(event)}>
    <div className="catalog-editor-fields">
      <Field label="库归属"><select disabled={Boolean(item)} value={draft.libraryScope} onChange={(event) => update('libraryScope', event.target.value)}><option value="general">通用动作库</option><option value="brand">品牌专属动作库</option></select></Field>
      {draft.libraryScope === 'brand' ? <Field label="所属品牌"><select required disabled={Boolean(item)} value={draft.brandId} onChange={(event) => update('brandId', event.target.value)}><option value="">请选择品牌</option>{profiles.filter((profile) => profile.libraryScope === 'brand').map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select></Field> : null}
      {draft.libraryScope === 'brand' ? <Field label="通用基础动作" hint="品牌动作只补充表情、力度、节奏或镜头配合。"><select required disabled={Boolean(item)} value={draft.baseActionId} onChange={(event) => update('baseActionId', event.target.value)}><option value="">请选择通用动作</option>{actions.filter((action) => action.libraryScope === 'general').map((action) => <option key={action.id} value={action.id}>{action.label}</option>)}</select></Field> : null}
      <Field label="动作 ID" hint="保存后不可修改；英文小写与下划线。"><input required disabled={Boolean(item)} value={draft.id} onChange={(event) => update('id', event.target.value)} placeholder="例如 sleeve_detail_pause" /></Field>
      <Field label="显示名称"><input required value={draft.label} onChange={(event) => update('label', event.target.value)} placeholder="例如 袖口细节停留" /></Field>
      <Field label="动作分类"><select value={draft.category} onChange={(event) => update('category', event.target.value)}><option value="outfit">整体穿搭</option><option value="detail">图案与面料</option><option value="back">背面展示</option><option value="interaction">人镜交流</option><option value="product">商品交互</option></select></Field>
      <Field label="风险等级"><select value={draft.riskLevel} onChange={(event) => update('riskLevel', event.target.value)}><option value="low">低风险</option><option value="conditional">需满足前提</option></select></Field>
      <Field label={draft.libraryScope === 'brand' ? '风格化差异' : '动作指令'} wide hint={draft.libraryScope === 'brand' ? '只补充表情、动作力度、节奏或镜头配合，不重复基础动作骨架。' : '格式：起始姿态 → 单一动作路径 → 停稳后的商品画面。'}><textarea required rows={5} value={draft.instruction} onChange={(event) => update('instruction', event.target.value)} placeholder={draft.libraryScope === 'brand' ? '保持冷漠直视和更明确的肩线，让基础动作呈现受控攻击性；镜头以有限低机位增加张力。' : '从自然站姿开始，右手沿安全路径轻触袖口并停留；随后手臂自然放下，结束时袖口与胸前图案完整可见。'} /></Field>
      <Field label={draft.libraryScope === 'brand' ? '差异目的' : '商品目的'} wide><textarea required rows={2} value={draft.purpose} onChange={(event) => update('purpose', event.target.value)} placeholder={draft.libraryScope === 'brand' ? '说明这项差异如何形成品牌气质，同时保护商品呈现。' : '说明这个动作帮助展示什么商品信息。'} /></Field>
      <fieldset className="catalog-editor-field is-wide catalog-template-checks"><legend>适用模板</legend><div>{templates.map((template) => <label key={template.id}><input type="checkbox" checked={draft.compatibleTemplates.includes(template.id)} onChange={(event) => update('compatibleTemplates', event.target.checked ? [...draft.compatibleTemplates, template.id] : draft.compatibleTemplates.filter((id) => id !== template.id))} />{template.name}</label>)}</div></fieldset>
      <Field label="使用前提" wide hint="每行一项。"><textarea rows={3} value={draft.requirements} onChange={(event) => update('requirements', event.target.value)} placeholder={'输入中袖口与手部清晰可见\n手部路径不会遮挡核心图案'} /></Field>
      <Field label="避免事项" wide hint="每行一项，写可观察的失败表现。"><textarea rows={3} value={draft.avoid} onChange={(event) => update('avoid', event.target.value)} placeholder={'反复拉扯面料\n手部遮挡胸前图案'} /></Field>
    </div>
    <EditorAdvice kind="action" suggestions={suggestions} />
    <EditorFooter busy={busy} error={error} onClose={onClose} />
  </form>
}

function StyleEditor({
  item,
  initialScope,
  actions,
  onClose,
  onSaved,
}: {
  item?: SiteStyleProfileSummary
  initialScope?: 'general' | 'brand'
  actions: MotionActionSummary[]
  onClose: () => void
  onSaved: Props['onSaved']
}) {
  const [draft, setDraft] = useState(() => styleInitial(item, initialScope))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const update = (key: keyof typeof draft, value: string) => setDraft((current) => ({ ...current, [key]: value }))
  const suggestions = useMemo(() => {
    const next: string[] = []
    if (!/^[a-z][a-z0-9_-]*$/.test(draft.id)) next.push('ID 使用英文小写、数字、短横线或下划线。')
    if (draft.tone.split(/[、，,]/).filter(Boolean).length < 3) next.push('风格定位建议包含 3–5 个可观察特征，并补一句商品呈现边界。')
    if (!/(表情|视线|微笑|直视|姿态|肩线)/.test(draft.expressionLanguage)) next.push('人物表达需明确表情或视线，并说明姿态力度。')
    if (!/(镜头|中景|全身|近景|推进|固定|跟拍)/.test(draft.cameraLanguage)) next.push('镜头语言需写清景别、机位和允许的运动方式。')
    if (!/(秒|开场|先|建立)/.test(draft.openingRule)) next.push('开场规则建议包含时间或优先建立的商品信息。')
    if (!/(停|结束|回到|保持)/.test(draft.endingRule)) next.push('收束规则需明确最终景别、姿态和商品可见状态。')
    if (!fromLines(draft.productPriorities).length) next.push('至少列出一项商品呈现重点。')
    if (!fromLines(draft.forbiddenMismatches).length) next.push('至少列出一项禁止错配，防止风格词覆盖商品真实性。')
    if (draft.status === 'active' && draft.evidenceLevel !== 'verified_site') next.push('证据受限的风格只能保存为研究草稿，不能直接进入生产。')
    const unknownActions = fromLines(draft.preferredActions).filter((id) => !actions.some((action) => action.id === id))
    if (unknownActions.length) next.push(`未找到动作 ID：${unknownActions.join('、')}。`)
    const mismatchedActions = fromLines(draft.preferredActions).filter((id) => actions.some((action) => action.id === id && action.libraryScope === 'brand' && (draft.libraryScope !== 'brand' || action.brandId !== draft.id)))
    if (mismatchedActions.length) next.push(`不能关联其他品牌的专属动作：${mismatchedActions.join('、')}。`)
    return next
  }, [actions, draft])

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const payload: SiteStyleProfileWrite = {
        id: draft.id.trim(),
        status: draft.status as SiteStyleProfileWrite['status'],
        name: draft.name.trim(),
        siteUrl: draft.siteUrl.trim(),
        sourceUrls: fromLines(draft.sourceUrls),
        retrievedAt: draft.retrievedAt,
        evidenceLevel: draft.evidenceLevel as SiteStyleProfileWrite['evidenceLevel'],
        tone: draft.tone.trim(),
        expressionLanguage: draft.expressionLanguage.trim(),
        audience: draft.audience.trim(),
        palette: fromLines(draft.palette),
        typography: draft.typography.trim(),
        cameraLanguage: draft.cameraLanguage.trim(),
        openingRule: draft.openingRule.trim(),
        middleRule: draft.middleRule.trim(),
        endingRule: draft.endingRule.trim(),
        preferredShots: fromLines(draft.preferredShots),
        preferredActions: fromLines(draft.preferredActions),
        pacing: draft.pacing.trim(),
        productPriorities: fromLines(draft.productPriorities),
        forbiddenMismatches: fromLines(draft.forbiddenMismatches),
        researchNote: draft.researchNote.trim(),
        libraryScope: draft.libraryScope as SiteStyleProfileWrite['libraryScope'],
        brandId: draft.libraryScope === 'brand' ? draft.id.trim() : null,
      }
      const saved = item
        ? await updateSiteStyleProfile(item.id, payload)
        : await createSiteStyleProfile(payload)
      onSaved(saved, 'style')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '站点风格保存失败')
    } finally {
      setBusy(false)
    }
  }

  return <form className="catalog-editor-form" onSubmit={(event) => void save(event)}>
    <div className="catalog-editor-fields">
      <Field label="库归属"><select disabled={Boolean(item)} value={draft.libraryScope} onChange={(event) => update('libraryScope', event.target.value)}><option value="general">通用风格库</option><option value="brand">品牌专属风格库</option></select></Field>
      <Field label="风格 ID" hint="保存后不可修改。"><input required disabled={Boolean(item)} value={draft.id} onChange={(event) => update('id', event.target.value)} placeholder="例如 brand_name" /></Field>
      <Field label={draft.libraryScope === 'brand' ? '站点 / 品牌名称' : '风格名称'}><input required value={draft.name} onChange={(event) => update('name', event.target.value)} placeholder={draft.libraryScope === 'brand' ? '例如 品牌名 / Brand' : '例如 自然生活方式'} /></Field>
      <Field label="生产状态"><select value={draft.status} onChange={(event) => update('status', event.target.value)}><option value="draft">研究草稿</option><option value="active">已验证可用</option><option value="retired">已停用</option></select></Field>
      <Field label="证据状态"><select value={draft.evidenceLevel} onChange={(event) => update('evidenceLevel', event.target.value)}><option value="restricted_site">证据受限</option><option value="verified_site">站点已验证</option></select></Field>
      <Field label="证据复核日期"><input required type="date" value={draft.retrievedAt} onChange={(event) => update('retrievedAt', event.target.value)} /></Field>
      <Field label="站点地址" hint="仅作为证据记录，内容库不提供“访问站点”操作。"><input type="url" value={draft.siteUrl} onChange={(event) => update('siteUrl', event.target.value)} placeholder="https://example.com/" /></Field>
      <Field label="风格定位" wide hint="3–5 个可观察特征 + 商品呈现边界。"><textarea required rows={3} value={draft.tone} onChange={(event) => update('tone', event.target.value)} placeholder="轻快、克制、复古科技感；动作服务于商品识别，不使用高速炫技运镜。" /></Field>
      <Field label="人物表达" wide hint="写清表情、视线、姿态力度，以及明确禁止的表演方式。"><textarea required rows={3} value={draft.expressionLanguage} onChange={(event) => update('expressionLanguage', event.target.value)} placeholder="人物保持轻松好奇的表情，允许一次机灵掠视或自然微笑；动作轻快但不夸张，不遮挡商品。" /></Field>
      <Field label="目标受众" wide><textarea required rows={2} value={draft.audience} onChange={(event) => update('audience', event.target.value)} placeholder="描述站点真实服务的人群与穿搭场景。" /></Field>
      <Field label="开场规则" wide hint="建立人物、景别与第一个商品信息。"><textarea required rows={3} value={draft.openingRule} onChange={(event) => update('openingRule', event.target.value)} placeholder="前 2–3 秒以正面中景建立整件服装与核心图案，人物保持自然站姿。" /></Field>
      <Field label="中段规则" wide hint="只安排 1–2 个可验证动作。"><textarea required rows={3} value={draft.middleRule} onChange={(event) => update('middleRule', event.target.value)} placeholder="完成一次三分之四转身，并给面料或袖口一次稳定细节停留。" /></Field>
      <Field label="收束规则" wide hint="明确结束景别、姿态与无遮挡区域。"><textarea required rows={3} value={draft.endingRule} onChange={(event) => update('endingRule', event.target.value)} placeholder="回到正面中景自然定姿，保持图案、领口与下摆完整可见。" /></Field>
      <Field label="镜头语言" wide><textarea required rows={3} value={draft.cameraLanguage} onChange={(event) => update('cameraLanguage', event.target.value)} placeholder="稳定正面观察为主，允许一次缓慢推进与一次干净切镜，不使用甩镜。" /></Field>
      <Field label="节奏"><input required value={draft.pacing} onChange={(event) => update('pacing', event.target.value)} placeholder="slow_to_standard；细节停留 1–1.5 秒" /></Field>
      <Field label="字体倾向"><input required value={draft.typography} onChange={(event) => update('typography', event.target.value)} placeholder="清楚的几何无衬线" /></Field>
      <Field label="优先镜头" wide hint="每行一项。"><textarea required rows={3} value={draft.preferredShots} onChange={(event) => update('preferredShots', event.target.value)} placeholder={'正面中景\n三分之四中近景\n图案细节近景'} /></Field>
      <Field label="关联动作 ID" wide hint="每行一个动作 ID；可从动作提示词卡片复制。"><textarea rows={3} value={draft.preferredActions} onChange={(event) => update('preferredActions', event.target.value)} placeholder={'stance_shift\nthree_quarter_turn\nprint_detail_pause'} /></Field>
      <Field label="商品呈现重点" wide hint="每行一项。"><textarea required rows={3} value={draft.productPriorities} onChange={(event) => update('productPriorities', event.target.value)} placeholder={'整件版型\n图案和文字可读性\n袖口与下摆'} /></Field>
      <Field label="禁止错配" wide hint="每行一项，写明确不能出现的内容或动作。"><textarea required rows={3} value={draft.forbiddenMismatches} onChange={(event) => update('forbiddenMismatches', event.target.value)} placeholder={'高速旋转\n手部遮挡核心文字\n特效改变服装颜色'} /></Field>
      <Field label="色彩关键词" wide hint="每行一项；用于描述倾向，不覆盖输入商品颜色。"><textarea rows={2} value={draft.palette} onChange={(event) => update('palette', event.target.value)} placeholder={'washed neutral\nvintage accent'} /></Field>
      <Field label="证据来源" wide hint="每行一个 URL，仅作内部追溯。"><textarea rows={3} value={draft.sourceUrls} onChange={(event) => update('sourceUrls', event.target.value)} placeholder={'https://example.com/\nhttps://instagram.com/example'} /></Field>
      <Field label="研究说明" wide><textarea required rows={3} value={draft.researchNote} onChange={(event) => update('researchNote', event.target.value)} placeholder="说明哪些规则来自可见证据、哪些内容没有推断，以及生产边界。" /></Field>
    </div>
    <EditorAdvice kind="style" suggestions={suggestions} />
    <EditorFooter busy={busy} error={error} onClose={onClose} />
  </form>
}

function EditorAdvice({ kind, suggestions }: { kind: EditorTarget['kind']; suggestions: string[] }) {
  return <aside className="catalog-editor-advice" aria-label="修改建议">
    <div><Lightbulb size={18} /><span><strong>实时修改建议</strong><small>根据当前输入自动检查</small></span></div>
    {suggestions.length
      ? <ul>{suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}</ul>
      : <p className="catalog-advice-ready"><CheckCircle2 size={16} />结构完整，可以保存。</p>}
    <section>
      <strong>{kind === 'action' ? '动作提示词格式' : '站点风格格式'}</strong>
      {kind === 'action'
        ? <code>起始姿态 → 单一动作 → 停稳状态 → 商品保护</code>
        : <code>风格定位 → 开 / 承 / 收 → 镜头与节奏 → 商品重点 → 禁止错配 → 证据</code>}
      <p>{kind === 'action'
        ? '一个动作原子只解决一个展示目的；不要把走动、转身、拉衣摆和运镜堆在同一句里。'
        : '只写站点证据能支持的可观察规律，不从品牌名称、文化主题或人群标签推断表演。'}</p>
    </section>
  </aside>
}

function EditorFooter({ busy, error, onClose }: { busy: boolean; error: string; onClose: () => void }) {
  return <footer className="catalog-editor-footer">
    {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : <span />}
    <div><button className="secondary-button" type="button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy} type="submit">{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}{busy ? '正在保存' : '保存内容'}</button></div>
  </footer>
}

export function CatalogEditor({ target, actions, profiles, templates, onClose, onSaved }: Props) {
  useEffect(() => {
    const listener = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', listener)
    document.body.classList.add('modal-open')
    return () => {
      window.removeEventListener('keydown', listener)
      document.body.classList.remove('modal-open')
    }
  }, [onClose])

  const isEdit = Boolean(target.item)
  return createPortal(<div className="catalog-editor-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="catalog-editor" role="dialog" aria-modal="true" aria-labelledby="catalog-editor-title">
      <header className="catalog-editor-head">
        <div><span>{target.kind === 'action' ? 'Motion Prompt' : 'Site Style Profile'}</span><h2 id="catalog-editor-title">{isEdit ? '编辑' : '新增'}{target.kind === 'action' ? '动作提示词' : '站点视频风格'}</h2><p>{isEdit ? '保存后生成新版本，已创建任务不受影响。' : '先按格式写清可观察规则，再决定是否进入生产。'}</p></div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="关闭编辑器"><X size={19} /></button>
      </header>
      {target.kind === 'action'
        ? <ActionEditor item={target.item} initialScope={target.initialScope} actions={actions} profiles={profiles} templates={templates} onClose={onClose} onSaved={onSaved} />
        : <StyleEditor item={target.item} initialScope={target.initialScope} actions={actions} onClose={onClose} onSaved={onSaved} />}
    </section>
  </div>, document.body)
}
