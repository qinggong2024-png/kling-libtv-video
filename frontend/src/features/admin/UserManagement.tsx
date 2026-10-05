// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, CheckCircle2, KeyRound, LoaderCircle, LogOut, Plus, RefreshCw, UserRound } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { ApiError, changePassword, createAdminUser, deactivateAdminUser, getAdminUsers, resetAdminUserPassword } from '../../api'
import { type AdminUser } from '../../types'
import { formatTime } from '../../domain/taskPresentation'
import { EmptyState } from '../../shared/components/Section'

export function UserManagement({ adminId, sharedAuthentication }: { adminId: string; sharedAuthentication: boolean }) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [resetUserId, setResetUserId] = useState<string | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [changeOpen, setChangeOpen] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordConfirmation, setNewPasswordConfirmation] = useState('')
  const [busy, setBusy] = useState<string | null>('load')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      setUsers(await getAdminUsers(adminId))
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取账号列表')
    } finally {
      setBusy(null)
    }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedUsername = username.trim()
    if (!normalizedUsername || password.length < 12) return
    setBusy('create')
    setError('')
    setNotice('')
    try {
      const created = await createAdminUser(adminId, {
        username: normalizedUsername,
        password,
      })
      setUsers((current) => [...current, created].sort((left, right) => left.username.localeCompare(right.username, 'zh-CN')))
      setUsername('')
      setPassword('')
      setNotice(`账号“${created.username}”已创建，可以使用临时密码登录。`)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '账号创建失败')
    } finally {
      setBusy(null)
    }
  }

  const reset = async (event: FormEvent<HTMLFormElement>, user: AdminUser) => {
    event.preventDefault()
    if (resetPassword.length < 12) return
    setBusy(`reset:${user.id}`)
    setError('')
    setNotice('')
    try {
      await resetAdminUserPassword(adminId, user.id, resetPassword)
      setResetUserId(null)
      setResetPassword('')
      setNotice(`账号“${user.username}”的密码已重置，旧登录会话已失效。`)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '密码重置失败')
    } finally {
      setBusy(null)
    }
  }

  const changeOwnPassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (newPassword.length < 12 || newPassword !== newPasswordConfirmation) return
    setBusy('change-own-password')
    setError('')
    setNotice('')
    try {
      await changePassword(currentPassword, newPassword)
      setChangeOpen(false)
      setCurrentPassword('')
      setNewPassword('')
      setNewPasswordConfirmation('')
      setNotice('你的密码已修改，其他设备上的旧登录会话已退出。')
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'CURRENT_PASSWORD_INVALID') setError('当前密码不正确，请重新输入。')
      else if (cause instanceof ApiError && cause.code === 'PASSWORD_UNCHANGED') setError('新密码不能与当前密码相同。')
      else setError(cause instanceof ApiError ? cause.message : '密码修改失败')
    } finally {
      setBusy(null)
    }
  }

  const deactivate = async (user: AdminUser) => {
    if (!window.confirm(`停用账号“${user.username}”后，该账号会立即退出且无法继续登录。确定停用吗？`)) return
    setBusy(`deactivate:${user.id}`)
    setError('')
    setNotice('')
    try {
      await deactivateAdminUser(adminId, user.id)
      setUsers((current) => current.map((item) => item.id === user.id ? { ...item, isActive: false } : item))
      setNotice(`账号“${user.username}”已停用。`)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '账号停用失败')
    } finally {
      setBusy(null)
    }
  }

  const roleLabels: Record<AdminUser['role'], string> = {
    ADMIN: '管理员',
    OPERATOR: '运营人员',
    USER: '普通用户',
  }

  return <section className="settings-section account-management-section">
    <div className="settings-section-heading">
      <div><span>访问控制</span><h2>成员账号</h2><p>为局域网成员创建独立登录账号。新账号默认为普通用户，不能进入管理中心。</p></div>
      <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void load()}><RefreshCw className={busy === 'load' ? 'spin' : ''} size={16} />刷新列表</button>
    </div>
    <form className="account-create-form" onSubmit={(event) => void create(event)}>
      <label htmlFor="new-account-username"><span>登录账号</span><input id="new-account-username" name="username" value={username} onChange={(event) => setUsername(event.target.value)} minLength={1} maxLength={80} autoComplete="off" spellCheck={false} placeholder="例如：designer-01" required /><small>不能包含空格，创建后不可修改</small></label>
      <label htmlFor="new-account-password"><span>临时密码</span><input id="new-account-password" name="new-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" placeholder="至少 12 个字符" required /><small>请通过可信方式交给成员</small></label>
      <button className="primary-button" type="submit" disabled={busy !== null || !username.trim() || password.length < 12}>{busy === 'create' ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}{busy === 'create' ? '正在创建…' : '创建账号'}</button>
    </form>
    <div className="account-feedback" aria-live="polite">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
    <div className="account-list" aria-busy={busy === 'load'}>
      {users.map((user) => <article className={`account-row${user.isActive ? '' : ' is-inactive'}`} key={user.id}>
        <span className="account-avatar" aria-hidden="true"><UserRound size={18} /></span>
        <div className="account-identity"><strong>{user.username}</strong><span>{roleLabels[user.role]} · 创建于 {formatTime(user.createdAt)}</span></div>
        <span className={`account-state${user.isActive ? ' is-active' : ''}`}>{user.isActive ? '正常' : '已停用'}</span>
        {user.id === adminId && user.isActive && sharedAuthentication ? <div className="account-actions">
          <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => { setChangeOpen(true); setResetUserId(null); setCurrentPassword(''); setNewPassword(''); setNewPasswordConfirmation(''); setNotice(''); setError('') }}><KeyRound size={15} />修改密码</button>
        </div> : null}
        {user.role === 'USER' && user.isActive ? <div className="account-actions">
          <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => { setResetUserId(user.id); setResetPassword(''); setNotice(''); setError('') }}><KeyRound size={15} />重置密码</button>
          <button className="danger-button" type="button" disabled={busy !== null} onClick={() => void deactivate(user)}>{busy === `deactivate:${user.id}` ? <LoaderCircle className="spin" size={15} /> : <LogOut size={15} />}停用</button>
        </div> : null}
        {resetUserId === user.id ? <form className="account-reset-form" onSubmit={(event) => void reset(event, user)}>
          <label htmlFor={`reset-password-${user.id}`}><span>为“{user.username}”设置新密码</span><input id={`reset-password-${user.id}`} type="password" value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" placeholder="至少 12 个字符" required /></label>
          <div><button className="secondary-button" type="button" disabled={busy !== null} onClick={() => { setResetUserId(null); setResetPassword('') }}>取消</button><button className="primary-button" type="submit" disabled={busy !== null || resetPassword.length < 12}>{busy === `reset:${user.id}` ? <LoaderCircle className="spin" size={15} /> : <KeyRound size={15} />}确认重置</button></div>
        </form> : null}
        {user.id === adminId && changeOpen ? <form className="account-reset-form account-change-password-form" onSubmit={(event) => void changeOwnPassword(event)}>
          <label htmlFor="current-account-password"><span>当前密码</span><input id="current-account-password" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} maxLength={512} autoComplete="current-password" required /></label>
          <label htmlFor="new-account-password-self"><span>新密码</span><input id="new-account-password-self" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" placeholder="至少 12 个字符" required /></label>
          <label htmlFor="confirm-account-password-self"><span>确认新密码</span><input id="confirm-account-password-self" type="password" value={newPasswordConfirmation} onChange={(event) => setNewPasswordConfirmation(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" aria-invalid={Boolean(newPasswordConfirmation && newPassword !== newPasswordConfirmation)} required /></label>
          <div><button className="secondary-button" type="button" disabled={busy !== null} onClick={() => { setChangeOpen(false); setCurrentPassword(''); setNewPassword(''); setNewPasswordConfirmation('') }}>取消</button><button className="primary-button" type="submit" disabled={busy !== null || !currentPassword || newPassword.length < 12 || newPassword !== newPasswordConfirmation}>{busy === 'change-own-password' ? <LoaderCircle className="spin" size={15} /> : <KeyRound size={15} />}保存新密码</button></div>
        </form> : null}
      </article>)}
      {!users.length && busy !== 'load' ? <EmptyState icon={<UserRound size={24} />} title="还没有成员账号" description="创建第一个普通用户账号后，对方即可从登录页进入。" /> : null}
      {busy === 'load' ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取成员账号…</div> : null}
    </div>
  </section>
}
