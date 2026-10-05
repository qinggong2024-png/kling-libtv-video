// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, CheckCircle2, KeyRound, LoaderCircle, Trash2 } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { ApiError, changePassword, clearPersonalVideoLearning, getPersonalPromptAutoConfirmation, getPersonalVideoLearning, setPersonalPromptAutoConfirmation, setPersonalVideoLearning } from '../../api'
import { type VideoLearningPreference } from '../../types'

export function PersonalPromptConfirmationSetting() {
  const [automatic, setAutomatic] = useState(false)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const preference = await getPersonalPromptAutoConfirmation()
      setAutomatic(preference.automatic)
      setReady(true)
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取自动确认设置')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const toggle = async (enabled: boolean) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const preference = await setPersonalPromptAutoConfirmation(enabled)
      setAutomatic(preference.automatic)
      setNotice(preference.automatic
        ? '已开启，普通方案分析完成后将自动开始生成。'
        : '已关闭，后续方案会在生成前等待你确认。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '自动确认设置保存失败')
      await load()
    } finally {
      setBusy(false)
    }
  }

  return <section className="settings-section prompt-confirmation-section">
    <div className="settings-section-heading">
      <div><span>生成流程</span><h2>分析完成后自动开始生成</h2><p>{automatic ? '普通方案分析完成后会跳过人工确认并直接生成，可能立即消耗生成额度；需要质量复核或被系统拦截的方案仍需人工处理。' : '默认关闭。分析完成后会停在确认步骤，等你检查提示词并主动开始生成。'}</p></div>
      <div className="prompt-confirmation-control">
        <span className={`prompt-confirmation-state${automatic ? ' is-active' : ''}`}>{busy && !ready ? '读取中' : automatic ? '已开启' : '已关闭'}</span>
        <label className="settings-switch" title="分析完成后自动开始生成">
          <input type="checkbox" checked={automatic} disabled={busy || !ready} aria-label="分析完成后自动开始生成" onChange={(event) => void toggle(event.target.checked)} />
          <span aria-hidden="true" />
        </label>
      </div>
    </div>
    <div className="prompt-confirmation-feedback" aria-live="polite">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </section>
}

export function PersonalVideoLearningSetting() {
  const [preference, setPreference] = useState<VideoLearningPreference | null>(null)
  const [busy, setBusy] = useState<'load' | 'toggle' | 'clear' | null>('load')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      setPreference(await getPersonalVideoLearning())
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取成片学习设置')
    } finally {
      setBusy(null)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const toggle = async (enabled: boolean) => {
    setBusy('toggle')
    setError('')
    setNotice('')
    try {
      const next = await setPersonalVideoLearning(enabled)
      setPreference(next)
      setNotice(enabled ? '后续自动生成会应用你的成片偏好。' : '已暂停应用，已有记忆仍保留。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '成片学习设置保存失败')
      await load()
    } finally {
      setBusy(null)
    }
  }

  const clear = async () => {
    if (!window.confirm('确定清空你的全部成片反馈和已学习偏好吗？此操作无法撤销。')) return
    setBusy('clear')
    setError('')
    setNotice('')
    try {
      await clearPersonalVideoLearning()
      setPreference((current) => current ? {
        ...current,
        feedbackCount: 0,
        scopeCount: 0,
        summary: '尚未积累可应用的成片反馈',
        updatedAt: null,
      } : current)
      setNotice('成片反馈记忆已清空。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '成片反馈记忆清空失败')
    } finally {
      setBusy(null)
    }
  }

  const enabled = preference?.enabled ?? false
  const learned = (preference?.feedbackCount ?? 0) > 0
  return <section className="settings-section video-learning-section">
    <div className="settings-section-heading">
      <div><span>个性化生成</span><h2>根据成片反馈持续学习</h2><p>{preference?.summary ?? '正在读取个人成片偏好'}</p></div>
      <div className="prompt-confirmation-control">
        <span className={`prompt-confirmation-state${enabled ? ' is-active' : ''}`}>{busy === 'load' ? '读取中' : enabled ? '已开启' : '已关闭'}</span>
        <label className="settings-switch" title="根据成片反馈持续学习">
          <input type="checkbox" checked={enabled} disabled={busy !== null || !preference} aria-label="根据成片反馈持续学习" onChange={(event) => void toggle(event.target.checked)} />
          <span aria-hidden="true" />
        </label>
      </div>
    </div>
    <div className="video-learning-details">
      <div className="video-learning-stats" aria-label="个人成片学习统计">
        <span><strong>{preference?.feedbackCount ?? 0}</strong>条反馈</span>
        <span><strong>{preference?.scopeCount ?? 0}</strong>个生成风格</span>
      </div>
      <button className="danger-button" type="button" disabled={busy !== null || !learned} onClick={() => void clear()}>{busy === 'clear' ? <LoaderCircle className="spin" size={15} /> : <Trash2 size={15} />}{busy === 'clear' ? '正在清空' : '清空反馈记忆'}</button>
    </div>
    <div className="prompt-confirmation-feedback" aria-live="polite">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </section>
}

export function PersonalPasswordSetting() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!currentPassword || newPassword.length < 12 || newPassword !== confirmation) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmation('')
      setNotice('密码已修改，其他设备上的旧登录会话已退出。')
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'CURRENT_PASSWORD_INVALID') setError('当前密码不正确，请重新输入。')
      else if (cause instanceof ApiError && cause.code === 'PASSWORD_UNCHANGED') setError('新密码不能与当前密码相同。')
      else setError(cause instanceof ApiError ? cause.message : '密码修改失败')
    } finally {
      setBusy(false)
    }
  }

  return <section className="settings-section personal-password-section">
    <div className="settings-section-heading"><div><span>账号安全</span><h2>修改密码</h2><p>修改当前登录账号的密码。保存后，其他设备上的旧登录会话会自动退出。</p></div></div>
    <form className="personal-password-form" onSubmit={(event) => void save(event)}>
      <label htmlFor="settings-current-password"><span>当前密码</span><input id="settings-current-password" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} maxLength={512} autoComplete="current-password" required /></label>
      <label htmlFor="settings-new-password"><span>新密码</span><input id="settings-new-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" placeholder="至少 12 个字符" required /></label>
      <label htmlFor="settings-confirm-password"><span>确认新密码</span><input id="settings-confirm-password" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" aria-invalid={Boolean(confirmation && confirmation !== newPassword)} required /></label>
      <button className="primary-button" type="submit" disabled={busy || !currentPassword || newPassword.length < 12 || newPassword !== confirmation}>{busy ? <LoaderCircle className="spin" size={16} /> : <KeyRound size={16} />}{busy ? '正在保存' : '保存新密码'}</button>
    </form>
    <div className="account-feedback" aria-live="polite">{notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}{error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}</div>
  </section>
}
