// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, Check, CheckCircle2, CircleAlert, Clapperboard, LoaderCircle, LockKeyhole, RefreshCw, RotateCcw, X } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { ApiError, getKlingConfig, getKlingStatus, refreshKlingCapabilities, updateKlingConfig } from '../../api'
import { type KlingConfig, type KlingStatus } from '../../types'
import { type KlingConfigDraft, KLING_ASPECT_RATIO_OPTIONS, KLING_AUDIO_OPTIONS, KLING_BASE_URL_OPTIONS, KLING_MODEL_OPTIONS, KLING_RESOLUTION_OPTIONS, buildKlingConfigPatch, createKlingConfigDraft, formatKlingApiVersion, klingApiStatusPresentation, validateKlingConfig } from '../../klingConfig'

export function KlingProviderSettings({ adminId, onChanged }: { adminId: string; onChanged: () => Promise<void> }) {
  const [config, setConfig] = useState<KlingConfig | null>(null)
  const [draft, setDraft] = useState<KlingConfigDraft | null>(null)
  const [status, setStatus] = useState<KlingStatus | null>(null)
  const [busy, setBusy] = useState<'load' | 'save' | 'refresh' | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      const [nextConfig, nextStatus] = await Promise.all([
        getKlingConfig(adminId),
        getKlingStatus(adminId),
      ])
      setConfig(nextConfig)
      setDraft(createKlingConfigDraft(nextConfig))
      setStatus(nextStatus)
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取可灵官方 API 配置')
    } finally { setBusy(null) }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const updateDraft = <K extends keyof KlingConfigDraft>(field: K, value: KlingConfigDraft[K]) => {
    setDraft((current) => current ? { ...current, [field]: value } : current)
    setError('')
    setNotice('')
  }

  const refreshCapabilities = async () => {
    setBusy('refresh')
    setError('')
    setNotice('')
    try {
      setStatus(await refreshKlingCapabilities(adminId))
      setNotice('官方 API 连接与能力状态已刷新。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '验证官方 API 连接失败')
    } finally { setBusy(null) }
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!draft || !config) return
    const validationError = validateKlingConfig(draft, config.apiKeyConfigured)
    if (validationError) {
      setError(validationError)
      setNotice('')
      return
    }
    setBusy('save')
    setError('')
    setNotice('')
    try {
      const next = await updateKlingConfig(adminId, buildKlingConfigPatch(draft))
      setConfig(next)
      setDraft(createKlingConfigDraft(next))
      setNotice('可灵官方 API 配置已保存；后续新任务使用新配置，已提交任务不受影响。')
      await onChanged()
      setStatus(await getKlingStatus(adminId))
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '可灵官方 API 配置保存失败')
    } finally { setBusy(null) }
  }

  const isReady = Boolean(status?.available && status.authenticated)
  const apiState = klingApiStatusPresentation(status?.status, status?.enabled, status?.reason)
  const apiVersion = formatKlingApiVersion(status?.cliVersion)

  const apiKeyWillExist = Boolean(draft?.apiKey.trim()) || Boolean(config?.apiKeyConfigured && !draft?.clearApiKey)
  const hasChanges = Boolean(config && draft && (
    draft.backend !== config.backend
    || draft.baseUrl.trim() !== (config.baseUrl ?? '')
    || draft.callbackUrl.trim() !== (config.callbackUrl ?? '')
    || draft.model !== config.model
    || draft.duration !== config.duration
    || draft.aspectRatio !== config.aspectRatio
    || draft.resolution !== config.resolution
    || draft.audio !== config.audio
    || draft.multiShot !== config.multiShot
    || draft.maxSubmitConcurrency !== config.maxSubmitConcurrency
    || draft.maxPollConcurrency !== config.maxPollConcurrency
    || draft.enabled !== config.enabled
    || draft.apiKey.trim()
    || draft.clearApiKey
  ))

  return <form className="settings-section kling-provider-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>可灵官方 API</span><h2>生产生成配置</h2><p>所有新任务固定通过官方 API 提交。密钥、区域和生成参数在保存后立即用于后续任务。</p></div>
      <div className="provider-actions">
        <button className="secondary-button" type="button" disabled={busy !== null || !status?.enabled} onClick={() => void refreshCapabilities()}><RefreshCw className={busy === 'refresh' ? 'spin' : ''} size={16} />验证 API 状态</button>
        <button className="primary-button" type="submit" disabled={busy !== null || !hasChanges}>{busy === 'save' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{busy === 'save' ? '正在保存' : '保存 API 配置'}</button>
      </div>
    </div>

    {busy === 'load' && !draft ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取可灵配置…</div> : null}
    {draft ? <>
      <div className="kling-provider-toolbar">
        <div className="api-status-card">
          <div className="api-status-card-icon"><Clapperboard size={20} /></div>
          <div><small>官方 API 状态{apiVersion ? ` · ${apiVersion}` : ''}</small><strong>{apiState.label}</strong><span>{status ? apiState.message : '正在读取官方 API 状态'}</span></div>
          <span className={`api-status-state is-${apiState.tone}`}>{busy === 'refresh' ? <LoaderCircle className="spin" size={13} /> : isReady ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />}{apiState.label}</span>
        </div>
        <div className="kling-enabled-control">
          <span><strong>启用官方 API</strong><small>{draft.enabled ? '验证通过后新任务可以提交到官方 API' : '新任务不会提交到可灵'}</small></span>
          <label className="settings-switch">
            <input type="checkbox" checked={draft.enabled} disabled={busy !== null} aria-label="启用当前可灵 Provider" onChange={(event) => updateDraft('enabled', event.target.checked)} />
            <span aria-hidden="true" />
          </label>
        </div>
      </div>

      <div className="kling-config-block">
        <div className="kling-config-heading"><div><strong>API 凭据</strong><small>密钥仅发送到服务端保存，页面不会读取或回显原值。</small></div><span className={apiKeyWillExist ? 'is-configured' : 'is-missing'}>{apiKeyWillExist ? '已配置' : '未配置'}</span></div>
        <div className="kling-api-key-row">
          <div className="credential-field">
            <label htmlFor="kling-api-key"><strong>可灵 API Key</strong><small>{config?.apiKeyConfigured && !draft.clearApiKey ? '输入新 Key 将替换现有密钥' : '保存后输入框会自动清空'}</small></label>
            <div className="secret-input"><LockKeyhole size={16} /><input id="kling-api-key" type="password" value={draft.apiKey} onChange={(event) => setDraft((current) => current ? { ...current, apiKey: event.target.value, clearApiKey: false } : current)} placeholder={config?.apiKeyConfigured && !draft.clearApiKey ? '已配置 · 输入新 Key 进行替换' : '输入可灵官方 API Key'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} aria-describedby="kling-api-key-help" /></div>
            <small id="kling-api-key-help">为安全起见，已保存的 Key 永不回显；留空不会覆盖原值。</small>
          </div>
          <button className="danger-button" type="button" disabled={busy !== null || (!config?.apiKeyConfigured && !draft.apiKey)} onClick={() => setDraft((current) => current ? { ...current, apiKey: '', clearApiKey: !current.clearApiKey } : current)}>{draft.clearApiKey ? <RotateCcw size={15} /> : <X size={15} />}{draft.clearApiKey ? '取消清除' : '清除 API Key'}</button>
        </div>
        {draft.clearApiKey ? <div className="inline-alert inline-alert--warning"><AlertTriangle size={16} />保存后将清除现有 API Key。若仍要启用 API，请先输入新 Key。</div> : null}
      </div>

      <div className="kling-settings-grid">
        <label htmlFor="kling-base-url"><strong>API 区域</strong><select id="kling-base-url" value={draft.baseUrl} disabled={busy !== null} onChange={(event) => updateDraft('baseUrl', event.target.value)}>{KLING_BASE_URL_OPTIONS.map((value) => <option key={value} value={value}>{value.includes('beijing') ? '中国站 · 北京' : '海外站 · 新加坡'}</option>)}</select><small>{draft.baseUrl}</small></label>
        <label htmlFor="kling-callback-url"><strong>回调 URL</strong><input id="kling-callback-url" type="url" value={draft.callbackUrl} disabled={busy !== null} onChange={(event) => updateDraft('callbackUrl', event.target.value)} placeholder="https://example.com/api/kling/callback" autoComplete="url" spellCheck={false} maxLength={2048} /><small>可选；留空时由服务端轮询任务状态</small></label>
        <label htmlFor="kling-model"><strong>模型</strong><select id="kling-model" value={draft.model} disabled={busy !== null} onChange={(event) => updateDraft('model', event.target.value)}>{Array.from(new Set([...KLING_MODEL_OPTIONS, draft.model])).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label htmlFor="kling-duration"><strong>时长</strong><input id="kling-duration" type="number" min={3} max={15} step={1} value={draft.duration} disabled={busy !== null} onChange={(event) => updateDraft('duration', Number(event.target.value))} /><small>允许范围 3–15 秒</small></label>
        <label htmlFor="kling-aspect-ratio"><strong>画面比例</strong><select id="kling-aspect-ratio" value={draft.aspectRatio} disabled={busy !== null} onChange={(event) => updateDraft('aspectRatio', event.target.value)}>{Array.from(new Set([...KLING_ASPECT_RATIO_OPTIONS, draft.aspectRatio])).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label htmlFor="kling-resolution"><strong>分辨率</strong><select id="kling-resolution" value={draft.resolution} disabled={busy !== null} onChange={(event) => updateDraft('resolution', event.target.value)}>{Array.from(new Set([...KLING_RESOLUTION_OPTIONS, draft.resolution])).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label htmlFor="kling-audio"><strong>音频</strong><select id="kling-audio" value={draft.audio} disabled={busy !== null} onChange={(event) => updateDraft('audio', event.target.value)}>{KLING_AUDIO_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <label htmlFor="kling-submit-concurrency"><strong>提交并发</strong><input id="kling-submit-concurrency" type="number" min={1} max={20} step={1} value={draft.maxSubmitConcurrency} disabled={busy !== null} onChange={(event) => updateDraft('maxSubmitConcurrency', Number(event.target.value))} /><small>允许范围 1–20</small></label>
        <label htmlFor="kling-poll-concurrency"><strong>查询并发</strong><input id="kling-poll-concurrency" type="number" min={1} max={50} step={1} value={draft.maxPollConcurrency} disabled={busy !== null} onChange={(event) => updateDraft('maxPollConcurrency', Number(event.target.value))} /><small>允许范围 1–50</small></label>
        <label className="kling-inline-switch"><span><strong>多镜头</strong><small>允许模型在一次生成中规划多个镜头</small></span><span className="settings-switch"><input type="checkbox" checked={draft.multiShot} disabled={busy !== null} aria-label="启用可灵多镜头" onChange={(event) => updateDraft('multiShot', event.target.checked)} /><span aria-hidden="true" /></span></label>
      </div>
    </> : null}

    <div className="kling-provider-feedback" aria-live="polite" aria-atomic="true">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </form>
}
