// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, Check, CheckCircle2, CircleAlert, Globe2, Images, LoaderCircle, LockKeyhole, RefreshCw, RotateCcw, X } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { ApiError, getWaveSpeedConfig, updateWaveSpeedConfig, verifyWaveSpeedConfig } from '../../api'
import { type WaveSpeedConfig } from '../../types'
import { type WaveSpeedConfigDraft, createWaveSpeedConfigDraft, normalizeWaveSpeedConfig } from '../../wavespeedConfig'

export function WaveSpeedProviderSettings({ adminId, onChanged }: { adminId: string; onChanged: () => Promise<void> }) {
  const [config, setConfig] = useState<WaveSpeedConfig | null>(null)
  const [draft, setDraft] = useState<WaveSpeedConfigDraft | null>(null)
  const [busy, setBusy] = useState<'load' | 'save' | 'verify' | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      const next = normalizeWaveSpeedConfig(await getWaveSpeedConfig(adminId))
      setConfig(next)
      setDraft(createWaveSpeedConfigDraft(next))
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取 WaveSpeed API 配置')
    } finally { setBusy(null) }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const updateDraft = <K extends keyof WaveSpeedConfigDraft>(key: K, value: WaveSpeedConfigDraft[K]) => {
    setDraft((current) => current ? { ...current, [key]: value } : current)
    setNotice('')
    setError('')
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!config || !draft) return
    let parsedUrl: URL
    try { parsedUrl = new URL(draft.baseUrl.trim()) } catch { setError('请输入有效的 WaveSpeed API 根地址。'); return }
    if (!['https:', 'http:'].includes(parsedUrl.protocol)) { setError('WaveSpeed API 地址必须使用 HTTP 或 HTTPS。'); return }
    if (!/^[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)+$/.test(draft.videoModel.trim())) { setError('请输入有效的 WaveSpeed 视频模型 ID。'); return }
    if (!Number.isInteger(draft.videoDuration) || draft.videoDuration < 3 || draft.videoDuration > 15) { setError('WaveSpeed 视频时长必须是 3-15 秒之间的整数。'); return }
    if (!Number.isInteger(draft.maxSubmitConcurrency) || draft.maxSubmitConcurrency < 1 || draft.maxSubmitConcurrency > 50) { setError('WaveSpeed 提交并发必须是 1-50 之间的整数。'); return }
    if (!Number.isInteger(draft.maxPollConcurrency) || draft.maxPollConcurrency < 1 || draft.maxPollConcurrency > 50) { setError('WaveSpeed 查询并发必须是 1-50 之间的整数。'); return }
    setBusy('save')
    setNotice('')
    setError('')
    try {
      const next = normalizeWaveSpeedConfig(await updateWaveSpeedConfig(adminId, {
        enabled: draft.enabled,
        baseUrl: draft.baseUrl.trim(),
        maxSubmitConcurrency: draft.maxSubmitConcurrency,
        maxPollConcurrency: draft.maxPollConcurrency,
        videoModel: draft.videoModel.trim(),
        videoDuration: draft.videoDuration,
        videoAspectRatio: draft.videoAspectRatio,
        videoSound: draft.videoSound,
        ...(draft.apiKey.trim() ? { apiKey: draft.apiKey.trim() } : {}),
        ...(draft.clearApiKey ? { clearApiKey: true } : {}),
      }))
      setConfig(next)
      setDraft(createWaveSpeedConfigDraft(next))
      setNotice('WaveSpeed API 配置已保存，后续新图片和视频任务将使用新配置。')
      await onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'WaveSpeed API 配置保存失败')
    } finally { setBusy(null) }
  }

  const verify = async () => {
    setBusy('verify')
    setNotice('')
    setError('')
    try {
      const next = normalizeWaveSpeedConfig(await verifyWaveSpeedConfig(adminId))
      setConfig(next)
      setDraft((current) => current ? {
        ...current,
        enabled: next.enabled,
        baseUrl: next.baseUrl,
        maxSubmitConcurrency: next.maxSubmitConcurrency,
        maxPollConcurrency: next.maxPollConcurrency,
        videoModel: next.videoModel,
        videoDuration: next.videoDuration,
        videoAspectRatio: next.videoAspectRatio,
        videoSound: next.videoSound,
      } : createWaveSpeedConfigDraft(next))
      setNotice('WaveSpeed 连接状态已刷新；验证不会创建图片任务。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'WaveSpeed API 连接验证失败')
    } finally { setBusy(null) }
  }

  const credentialLabel = config?.credentialSource === 'admin'
    ? '管理员安全配置'
    : config?.credentialSource === 'environment'
      ? '环境变量配置'
      : '未配置'
  const statusLabel = config?.available ? '连接可用' : config?.enabled ? '等待验证' : '已停用'
  const apiKeyWillExist = Boolean(draft?.apiKey.trim()) || Boolean(config?.apiKeyConfigured && !draft?.clearApiKey)
  const hasChanges = Boolean(config && draft && (
    config.enabled !== draft.enabled
    || config.baseUrl !== draft.baseUrl.trim()
    || config.maxSubmitConcurrency !== draft.maxSubmitConcurrency
    || config.maxPollConcurrency !== draft.maxPollConcurrency
    || config.videoModel !== draft.videoModel.trim()
    || config.videoDuration !== draft.videoDuration
    || config.videoAspectRatio !== draft.videoAspectRatio
    || config.videoSound !== draft.videoSound
    || draft.apiKey.trim()
    || draft.clearApiKey
  ))

  return <form className="settings-section wavespeed-provider-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>WaveSpeed AI</span><h2>图片与视频生成 API</h2><p>为图片中心和可切换的视频生产通道提供生成能力。密钥保存后不会在页面回显。</p></div>
      <div className="provider-actions">
        <button className="secondary-button" type="button" disabled={busy !== null || !config?.enabled || !config.apiKeyConfigured} onClick={() => void verify()}><RefreshCw className={busy === 'verify' ? 'spin' : ''} size={16} />验证 API 状态</button>
        <button className="primary-button" type="submit" disabled={busy !== null || !hasChanges}>{busy === 'save' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{busy === 'save' ? '正在保存' : '保存 API 配置'}</button>
      </div>
    </div>

    {busy === 'load' && !draft ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取 WaveSpeed 配置…</div> : null}
    {draft ? <>
      <div className="kling-provider-toolbar">
        <div className="api-status-card">
          <div className="api-status-card-icon"><Images size={20} /></div>
          <div><small>WaveSpeed API 状态</small><strong>{statusLabel}</strong><span>{config?.reason || `凭据来源：${credentialLabel}`}</span></div>
          <span className={`api-status-state is-${config?.available ? 'success' : config?.enabled ? 'warning' : 'neutral'}`}>{busy === 'verify' ? <LoaderCircle className="spin" size={13} /> : config?.available ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />}{statusLabel}</span>
        </div>
        <div className="kling-enabled-control">
          <span><strong>启用 WaveSpeed</strong><small>{draft.enabled ? '验证通过后允许图片中心提交付费任务' : '图片中心不会提交新的 WaveSpeed 任务'}</small></span>
          <label className="settings-switch"><input type="checkbox" checked={draft.enabled} disabled={busy !== null} aria-label="启用 WaveSpeed Provider" onChange={(event) => updateDraft('enabled', event.target.checked)} /><span aria-hidden="true" /></label>
        </div>
      </div>

      <div className="kling-config-block">
        <div className="kling-config-heading"><div><strong>API 凭据</strong><small>新 Key 仅发送到服务端加密保存，GET 和 PATCH 响应均不包含密钥原文。</small></div><span className={apiKeyWillExist ? 'is-configured' : 'is-missing'}>{credentialLabel}</span></div>
        <div className="kling-api-key-row">
          <div className="credential-field">
            <label htmlFor="wavespeed-api-key"><strong>WaveSpeed API Key</strong><small>{config?.apiKeyConfigured && !draft.clearApiKey ? '输入新 Key 将替换当前配置' : '保存后输入框自动清空'}</small></label>
            <div className="secret-input"><LockKeyhole size={16} /><input id="wavespeed-api-key" type="password" value={draft.apiKey} disabled={busy !== null} onChange={(event) => setDraft((current) => current ? { ...current, apiKey: event.target.value, clearApiKey: false } : current)} placeholder={config?.apiKeyConfigured && !draft.clearApiKey ? '已配置 · 输入新 Key 进行替换' : '输入 WaveSpeed API Key'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} aria-describedby="wavespeed-api-key-help" /></div>
            <small id="wavespeed-api-key-help">留空不会覆盖现有 Key；已保存的 Key 永不回显。</small>
          </div>
          <button className="danger-button" type="button" disabled={busy !== null || (config?.credentialSource !== 'admin' && !draft.apiKey)} onClick={() => setDraft((current) => current ? { ...current, apiKey: '', clearApiKey: !current.clearApiKey } : current)}>{draft.clearApiKey ? <RotateCcw size={15} /> : <X size={15} />}{draft.clearApiKey ? '取消清除' : '清除后台 Key'}</button>
        </div>
        {draft.clearApiKey ? <div className="inline-alert inline-alert--warning"><AlertTriangle size={16} />保存后将清除管理员配置的 Key。环境变量存在时将自动切换到环境变量。</div> : null}
      </div>

      <div className="wavespeed-endpoint-row">
        <label htmlFor="wavespeed-base-url"><strong>API 根地址</strong><div className="secret-input"><Globe2 size={16} /><input id="wavespeed-base-url" type="url" value={draft.baseUrl} disabled={busy !== null} onChange={(event) => updateDraft('baseUrl', event.target.value)} placeholder="https://api.wavespeed.ai/api/v3" autoComplete="url" spellCheck={false} maxLength={2048} /></div><small>由服务端校验并用于后续新任务；已提交任务不受影响。</small></label>
        <dl><dt>凭据来源</dt><dd>{credentialLabel}</dd><dt>服务状态</dt><dd>{config?.status || 'UNKNOWN'}</dd><dt>最近验证</dt><dd>{config?.checkedAt ? new Date(config.checkedAt).toLocaleString('zh-CN') : '尚未验证'}</dd></dl>
      </div>

      <div className="kling-config-block">
        <div className="kling-config-heading"><div><strong>视频生成参数</strong><small>选择 WaveSpeed 视频通道后，新任务使用这里保存的模型与输出规格。</small></div><span className={config?.videoBackendActive ? 'is-configured' : 'is-missing'}>{config?.videoBackendActive ? '当前视频通道' : '备用视频通道'}</span></div>
        <div className="kling-settings-grid">
          <label htmlFor="wavespeed-video-model"><strong>视频模型 ID</strong><input id="wavespeed-video-model" type="text" value={draft.videoModel} disabled={busy !== null} onChange={(event) => updateDraft('videoModel', event.target.value)} placeholder="kwaivgi/kling-video-o3-pro/reference-to-video" spellCheck={false} maxLength={255} /><small>{config?.videoProvider || 'wavespeed_video'}</small></label>
          <label htmlFor="wavespeed-video-duration"><strong>视频时长</strong><input id="wavespeed-video-duration" type="number" min={3} max={15} step={1} value={draft.videoDuration} disabled={busy !== null} onChange={(event) => updateDraft('videoDuration', Number(event.target.value))} /><small>允许范围 3-15 秒</small></label>
          <label htmlFor="wavespeed-video-aspect-ratio"><strong>画面比例</strong><select id="wavespeed-video-aspect-ratio" value={draft.videoAspectRatio} disabled={busy !== null} onChange={(event) => updateDraft('videoAspectRatio', event.target.value)}><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option></select></label>
          <label htmlFor="wavespeed-submit-concurrency"><strong>提交并发</strong><input id="wavespeed-submit-concurrency" type="number" min={1} max={50} step={1} value={draft.maxSubmitConcurrency} disabled={busy !== null} onChange={(event) => updateDraft('maxSubmitConcurrency', Number(event.target.value))} /><small>图片与视频共用</small></label>
          <label htmlFor="wavespeed-poll-concurrency"><strong>查询并发</strong><input id="wavespeed-poll-concurrency" type="number" min={1} max={50} step={1} value={draft.maxPollConcurrency} disabled={busy !== null} onChange={(event) => updateDraft('maxPollConcurrency', Number(event.target.value))} /><small>图片与视频共用</small></label>
          <label className="kling-inline-switch"><span><strong>生成声音</strong><small>请求 WaveSpeed 视频模型生成原生声音</small></span><span className="settings-switch"><input type="checkbox" checked={draft.videoSound} disabled={busy !== null} aria-label="启用 WaveSpeed 视频声音" onChange={(event) => updateDraft('videoSound', event.target.checked)} /><span aria-hidden="true" /></span></label>
        </div>
      </div>
    </> : null}

    <div className="kling-provider-feedback" aria-live="polite" aria-atomic="true">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </form>
}
