// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, Check, CheckCircle2, Eye, EyeOff, Globe2, LoaderCircle, LockKeyhole } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { ApiError, getAdminCredentials, getKlingConfig, updateAdminCredentials, updateKlingConfig } from '../../api'
import { type AdminCredentialsStatus, type KlingConfig } from '../../types'
import { formatTime } from '../../domain/taskPresentation'

function validateCompatibleBaseUrl(value: string): string {
  const normalized = value.trim()
  if (!normalized) return ''
  try {
    const url = new URL(normalized)
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) return '请使用 HTTPS；仅本机地址允许 HTTP。'
    if (url.username || url.password || url.search || url.hash) return '地址不能包含账号密码、查询参数或片段。'
  } catch { return '请输入完整地址，例如 https://gateway.example.com/v1。' }
  return ''
}
export function ProviderCredentials({ adminId }: { adminId: string | null }) {
  const [status, setStatus] = useState<AdminCredentialsStatus | null>(null)
  const [modelKey, setModelKey] = useState('')
  const [modelBaseUrl, setModelBaseUrl] = useState('')
  const [baseUrlError, setBaseUrlError] = useState('')
  const [showModel, setShowModel] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let active = true
    getAdminCredentials(adminId)
      .then((next) => { if (active) { setStatus(next); setModelBaseUrl(next.modelBaseUrl ?? ''); setError('') } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '无法读取管理员配置') })
    return () => { active = false }
  }, [adminId])

  const save = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault()
    const modelApiKey = modelKey.trim()
    const normalizedBaseUrl = modelBaseUrl.trim()
    const baseUrlChanged = normalizedBaseUrl !== (status?.modelBaseUrl ?? '')
    const nextBaseUrlError = validateCompatibleBaseUrl(normalizedBaseUrl)
    setBaseUrlError(nextBaseUrlError)
    if (nextBaseUrlError) return
    if (!modelApiKey && !baseUrlChanged) {
      setError('请至少更新一项分析服务配置')
      return
    }
    setBusy(true)
    setError('')
    setSaved(false)
    try {
      const next = await updateAdminCredentials(adminId, {
        ...(modelApiKey ? { modelApiKey } : {}),
        ...(baseUrlChanged && normalizedBaseUrl ? { modelBaseUrl: normalizedBaseUrl } : {}),
        ...(baseUrlChanged && !normalizedBaseUrl ? { clearModelBaseUrl: true } : {}),
      })
      setStatus(next)
      setModelBaseUrl(next.modelBaseUrl ?? '')
      setModelKey('')
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2200)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Key 保存失败') }
    finally { setBusy(false) }
  }

  const credentialState = (configured: boolean | undefined) => {
    if (status === null && !error) return '正在读取'
    return configured ? '已配置' : '未配置'
  }
  const hasChanges = Boolean(
    modelKey.trim()
    || modelBaseUrl.trim() !== (status?.modelBaseUrl ?? ''),
  )

  return <form className="settings-section credential-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>仅管理员</span><h2>分析服务凭据</h2><p>此处只管理方案分析服务；可灵 API Key 请在“可灵官方 API”页维护。密钥只保存在服务端且不会回显。</p></div>
      <button className="primary-button" type="submit" disabled={busy || !hasChanges}>{busy ? <LoaderCircle className="spin" size={16} /> : saved ? <Check size={16} /> : <LockKeyhole size={16} />}{busy ? '正在保存' : saved ? '已安全保存' : '保存配置'}</button>
    </div>
    <div className="credential-grid">
      <div className="credential-field">
        <label htmlFor="model-api-key"><strong>大模型 API Key</strong><small className={status?.modelConfigured ? 'is-configured' : ''}>{credentialState(status?.modelConfigured)}</small></label>
        <div className="secret-input"><LockKeyhole size={16} /><input id="model-api-key" type={showModel ? 'text' : 'password'} value={modelKey} onChange={(event) => setModelKey(event.target.value)} placeholder={status?.modelConfigured ? '输入新 Key 以替换当前配置' : '输入大模型 API Key'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} aria-describedby="model-key-help" /><button type="button" onClick={() => setShowModel((value) => !value)} aria-label={showModel ? '隐藏大模型 Key' : '显示大模型 Key'} title={showModel ? '隐藏' : '显示'}>{showModel ? <EyeOff size={16} /> : <Eye size={16} />}</button></div>
        <small id="model-key-help">用于服装、人物、场景分析和视频方案生成。</small>
      </div>
      <div className="credential-field credential-field--wide">
        <label htmlFor="model-base-url"><strong>OpenAI 兼容 Base URL</strong><small>{status?.modelBaseUrl ? '自定义' : '官方默认'}</small></label>
        <div className="secret-input"><Globe2 size={16} /><input id="model-base-url" type="url" value={modelBaseUrl} onChange={(event) => { setModelBaseUrl(event.target.value); if (baseUrlError) setBaseUrlError('') }} onBlur={() => setBaseUrlError(validateCompatibleBaseUrl(modelBaseUrl))} placeholder="https://gateway.example.com/v1" autoComplete="url" spellCheck={false} maxLength={2048} aria-describedby={`model-base-url-help${baseUrlError ? ' model-base-url-error' : ''}`} aria-invalid={Boolean(baseUrlError)} /></div>
        <small id="model-base-url-help">第三方 OpenAI 兼容服务需填写完整 API 根地址，通常以 /v1 结尾；留空使用官方 OpenAI。</small>
        {baseUrlError ? <small id="model-base-url-error" className="field-error" role="alert">{baseUrlError}</small> : null}
      </div>
    </div>
    <div className="credential-feedback" aria-live="polite">
      {status?.updatedAt ? <p className="credential-updated">最近更新：{formatTime(status.updatedAt)}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger credential-error" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </form>
}

export function ProviderRoutingSettings({ adminId, onChanged }: { adminId: string; onChanged: () => Promise<void> }) {
  const [currentBackend, setCurrentBackend] = useState<KlingConfig['backend'] | null>(null)
  const [videoBackend, setVideoBackend] = useState<KlingConfig['backend']>('api')
  const [busy, setBusy] = useState<'load' | 'save' | null>('load')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      const config = await getKlingConfig(adminId)
      setCurrentBackend(config.backend)
      setVideoBackend(config.backend)
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取生成通道路由')
    } finally { setBusy(null) }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (currentBackend === null || currentBackend === videoBackend) return
    setBusy('save')
    setError('')
    setNotice('')
    try {
      const config = await updateKlingConfig(adminId, { backend: videoBackend })
      setCurrentBackend(config.backend)
      setVideoBackend(config.backend)
      setNotice('生成通道路由已更新，仅影响后续新提交的任务。')
      await onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '生成通道路由切换失败')
    } finally { setBusy(null) }
  }

  const videoHelp = videoBackend === 'api'
    ? '使用可灵官方 API 的模型和视频参数。'
    : videoBackend === 'wavespeed'
      ? '使用下方 WaveSpeed 视频模型和参数。'
      : '使用下方 Bach Image-to-Video 模型和参数。'

  return <form className="settings-section provider-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>Provider Routing</span><h2>生成通道路由</h2><p>统一选择图片和视频任务使用的提供商。切换只影响后续新任务，历史任务仍由原提供商查询和下载。</p></div>
      <button className="primary-button" type="submit" disabled={busy !== null || currentBackend === null || currentBackend === videoBackend}>{busy === 'save' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{busy === 'save' ? '正在切换' : '应用通道路由'}</button>
    </div>
    {busy === 'load' && currentBackend === null ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取通道路由…</div> : null}
    {currentBackend !== null ? <div className="kling-settings-grid">
      <label htmlFor="image-provider-route"><strong>图片通道</strong><select id="image-provider-route" value="wavespeed" disabled><option value="wavespeed">WaveSpeed Image API</option></select><small>当前仅接入 WaveSpeed；Bach 图片能力将在 P4 阶段开放。</small></label>
      <label htmlFor="video-provider-route"><strong>视频通道</strong><select id="video-provider-route" value={videoBackend} disabled={busy !== null} onChange={(event) => setVideoBackend(event.target.value as KlingConfig['backend'])}><option value="api">可灵官方 API</option><option value="wavespeed">WaveSpeed 视频 API</option><option value="bach">Bach Image-to-Video</option></select><small>{videoHelp}</small></label>
    </div> : null}
    <div className="kling-provider-feedback" aria-live="polite" aria-atomic="true">{notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}{error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}</div>
  </form>
}
