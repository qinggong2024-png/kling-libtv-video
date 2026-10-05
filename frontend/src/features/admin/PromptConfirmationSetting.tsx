// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { ApiError, getOperations, setPromptAutoConfirmation } from '../../api'

export function PromptConfirmationSetting({ adminId }: { adminId: string }) {
  const [runtime, setRuntime] = useState<{ version: number; promptConfirmationRequired: boolean } | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const snapshot = await getOperations(adminId)
      setRuntime({
        version: snapshot.runtime.version,
        promptConfirmationRequired: snapshot.runtime.config.promptConfirmationRequired !== false,
      })
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取提示词确认设置')
    } finally {
      setBusy(false)
    }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const toggle = async (automatic: boolean) => {
    if (!runtime) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated = await setPromptAutoConfirmation(adminId, runtime.version, automatic)
      setRuntime({
        version: updated.version,
        promptConfirmationRequired: updated.config.promptConfirmationRequired !== false,
      })
      setNotice(automatic
        ? '自动确认已开启，普通方案分析完成后将直接进入生成。'
        : '自动确认已关闭，后续方案需要人工确认后才会生成。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '提示词确认设置保存失败')
      await load()
    } finally {
      setBusy(false)
    }
  }

  const automatic = runtime?.promptConfirmationRequired === false
  return <section className="settings-section prompt-confirmation-section">
    <div className="settings-section-heading">
      <div><span>生成流程</span><h2>自动确认提示词</h2><p>{automatic ? '普通方案分析完成后将跳过人工确认，直接进入生成流程。需要质量复核或被系统拦截的方案仍需人工处理。' : '默认关闭。方案分析完成后，需要人工检查并确认提示词才会开始生成。'}</p></div>
      <div className="prompt-confirmation-control">
        <span className={`prompt-confirmation-state${automatic ? ' is-active' : ''}`}>{busy && !runtime ? '读取中' : automatic ? '已开启' : '已关闭'}</span>
        <label className="settings-switch" title="自动确认提示词">
          <input type="checkbox" checked={automatic} disabled={busy || !runtime} aria-label="自动确认提示词" onChange={(event) => void toggle(event.target.checked)} />
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
