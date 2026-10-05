// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, Eye, EyeOff, KeyRound, LoaderCircle, LogIn, ShieldCheck, UserRound } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { ApiError, login } from '../../api'
import { LoginFlowLines } from '../../LoginFlowLines'
import { ProductLogo } from '../../shared/components/ProductLogo'

function loginErrorMessage(cause: unknown): string {
  if (!(cause instanceof ApiError)) return '无法连接生产服务，请检查网络后重试'
  if (cause.status === 401) return '账号或密码不正确，请重新输入'
  if (cause.status === 408) return '生产服务响应超时，请稍后重试'
  if (cause.status === 409) return '当前服务尚未启用团队账号登录'
  if (cause.status >= 500) return '生产服务暂时不可用，请稍后重试'
  return cause.message || '登录失败，请稍后重试'
}

export function LoginScreen({ onAuthenticated }: { onAuthenticated: () => Promise<void> }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    document.body.classList.add('login-open')
    return () => document.body.classList.remove('login-open')
  }, [])
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username.trim(), password)
      await onAuthenticated()
    } catch (cause) {
      setError(loginErrorMessage(cause))
    } finally { setBusy(false) }
  }
  return <main className="login-view">
    <section className="login-shell" aria-label="衣影工坊账号登录">
      <aside className="login-brand-panel">
        <LoginFlowLines />
        <ProductLogo />
        <div className="login-brand-copy">
          <span>KLING API PRODUCTION</span>
          <h1>衣影工坊</h1>
          <p>视频生产管理系统</p>
        </div>
        <div className="login-environment"><span aria-hidden="true" />团队生产环境</div>
      </aside>
      <form className="login-panel" onSubmit={(event) => void submit(event)} aria-busy={busy}>
        <div className="login-mobile-brand"><ProductLogo /></div>
        <div className="login-heading"><span>账号登录</span><h2>欢迎回来</h2><p>使用管理员分配的生产账号进入工作台。</p></div>
        <div className="login-field">
          <label htmlFor="login-username">账号</label>
          <span className="login-input-wrap"><UserRound size={18} aria-hidden="true" /><input id="login-username" name="username" value={username} onChange={(event) => { setUsername(event.target.value); setError('') }} autoComplete="username" autoCapitalize="none" spellCheck={false} disabled={busy} aria-invalid={Boolean(error)} aria-describedby={error ? 'login-error' : undefined} autoFocus required /></span>
        </div>
        <div className="login-field">
          <label htmlFor="login-password">密码</label>
          <span className="login-input-wrap"><KeyRound size={18} aria-hidden="true" /><input id="login-password" name="password" type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => { setPassword(event.target.value); setError('') }} autoComplete="current-password" disabled={busy} aria-invalid={Boolean(error)} aria-describedby={error ? 'login-error' : undefined} required /><button type="button" className="login-password-toggle" onClick={() => setShowPassword((current) => !current)} disabled={busy} aria-label={showPassword ? '隐藏密码' : '显示密码'} title={showPassword ? '隐藏密码' : '显示密码'}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></span>
        </div>
        <div className="login-feedback" aria-live="polite">
          {error ? <div id="login-error" className="inline-alert inline-alert--danger login-error" role="alert"><AlertTriangle size={17} />{error}</div> : null}
        </div>
        <button className="primary-button primary-button--large" type="submit" disabled={busy || !username.trim() || !password}>{busy ? <LoaderCircle className="spin" size={18} /> : <LogIn size={18} />}{busy ? '正在验证账号' : '登录'}</button>
        <p className="login-security-note"><ShieldCheck size={16} aria-hidden="true" />账号权限和操作记录由系统统一管理</p>
      </form>
    </section>
  </main>
}
