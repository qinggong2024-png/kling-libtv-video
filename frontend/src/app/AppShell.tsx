// 本文件由 App.tsx 拆分生成（2026-09-21 前端架构拆分 v1）。
// 应用外壳：跳转链接 + 侧边栏 + 移动端顶栏 + 底部导航 + ErrorBoundary 边界。
// JSX 为逐字搬运，类名、aria 属性、导航项计算方式均未改动。
import type { ComponentProps, ReactNode } from 'react'
import { HelpCircle, Settings, UserRound } from 'lucide-react'
import { ErrorBoundary } from '../ErrorBoundary'
import { ProductLogo } from '../shared/components/ProductLogo'
import type { AuthUser, SystemStatus } from '../types'
import type { View } from './appTypes'
import type { ProductSurface } from './productNavigation'

export type NavItem = { value: View; label: string; icon: ReactNode; badge?: number }
export type ProductNavItem = { value: ProductSurface; label: string; icon: ReactNode }

type Props = {
  nav: NavItem[]
  productNav: ProductNavItem[]
  surface: ProductSurface | null
  view: View
  onSwitchView: (next: View) => void
  onNavigateSurface: (next: ProductSurface) => void
  actor: AuthUser | null
  system: SystemStatus | null
  error: string
  currentProviderLabel: string
  sidebarInfo: 'account' | 'help' | null
  onSidebarInfoChange: (next: 'account' | 'help' | null) => void
  devActorRole: 'user' | 'admin'
  onSwitchDevelopmentActor: () => void
  onSignOut: () => void
  errorResetKeys: ComponentProps<typeof ErrorBoundary>['resetKeys']
  onErrorBack: () => void
  children: ReactNode
  projectContext?: ReactNode
  overlays: ReactNode
}

export function AppShell({
  nav,
  productNav,
  surface,
  view,
  onSwitchView,
  onNavigateSurface,
  actor,
  system,
  error,
  currentProviderLabel,
  sidebarInfo,
  onSidebarInfoChange,
  devActorRole,
  onSwitchDevelopmentActor,
  onSignOut,
  errorResetKeys,
  onErrorBack,
  children,
  projectContext,
  overlays,
}: Props) {
  const mobileNav = nav.filter((item) => item.value !== 'admin')
  const roleLabel = actor?.role === 'ADMIN' ? '管理员' : actor?.role === 'OPERATOR' ? '运营人员' : '普通用户'

  return <div className={`app-shell${view === 'make' ? ' app-shell--video' : ''}`}>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <aside className="sidebar">
      <ProductLogo subtitle={currentProviderLabel} />
      <nav className="product-nav" aria-label="Creative OS 导航">
        <span className="product-nav__section">Creative OS</span>
        {productNav.map((item) => <button key={item.value} type="button" aria-current={surface === item.value ? 'page' : undefined} onClick={() => onNavigateSurface(item.value)} className={surface === item.value ? 'is-active' : ''}>{item.icon}<span>{item.label}</span></button>)}
      </nav>
      <nav className="sidebar-main-nav legacy-nav" aria-label="操作导航">
        <span className="product-nav__section">操作</span>
        {nav.filter((item) => item.value !== 'settings').map((item) => <button key={item.value} type="button" aria-current={surface === null && view === item.value ? 'page' : undefined} onClick={() => onSwitchView(item.value)} className={surface === null && view === item.value ? 'is-active' : ''}>{item.icon}<span>{item.label}</span>{item.badge ? <i>{item.badge}</i> : null}</button>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-status"><span className={error ? 'is-offline' : ''} /><span>{error ? '服务连接异常' : system?.environment === 'test' ? '测试版' : '正式版'}</span></div>
        <button className={`sidebar-settings ${surface === null && view === 'settings' ? 'is-active' : ''}`} onClick={() => onSwitchView('settings')}><Settings size={18} /><span>设置</span></button>
        <div className="sidebar-utility"><button onClick={() => onSidebarInfoChange(sidebarInfo === 'help' ? null : 'help')} aria-label="帮助" title="帮助"><HelpCircle size={17} /></button><button onClick={() => onSidebarInfoChange(sidebarInfo === 'account' ? null : 'account')} aria-label="账号" title="账号"><UserRound size={17} /></button></div>
        {sidebarInfo ? <div className="sidebar-popover" role="status"><strong>{sidebarInfo === 'help' ? '制作帮助' : '当前账号'}</strong><p>{sidebarInfo === 'help' ? '上传服装与参考图后，确认方案即可开始生成。历史视频可在记录中继续处理。' : `${actor?.username ?? '生产账号'} · ${roleLabel}`}</p>{sidebarInfo === 'account' && system?.sharedAuthentication ? <button onClick={onSignOut}>退出登录</button> : sidebarInfo === 'account' && system?.phaseOneAdminId ? <button onClick={onSwitchDevelopmentActor}>切换为{devActorRole === 'admin' ? '普通用户' : '管理员'}</button> : <button onClick={() => onSidebarInfoChange(null)}>关闭</button>}</div> : null}
      </div>
    </aside>
    <div className="app-body">
      <header className="mobile-topbar"><ProductLogo subtitle={currentProviderLabel} /><div className="mobile-topbar-actions">{view === 'make' ? <button type="button" className="icon-button" aria-label="帮助" title="帮助" aria-expanded={sidebarInfo === 'help'} onClick={() => onSidebarInfoChange(sidebarInfo === 'help' ? null : 'help')}><HelpCircle size={18} aria-hidden="true" /></button> : null}<div className="service-state"><span className={error ? 'is-offline' : ''} />{error ? '服务异常' : system?.environment === 'test' ? '测试版' : '正式版'}</div></div></header>
      {view === 'make' && sidebarInfo === 'help' ? <section className="mobile-studio-help" aria-label="制作帮助"><strong>制作帮助</strong><p>上传服装与参考图后，确认方案即可开始生成。历史视频可在记录中继续处理。</p><button type="button" className="text-button" onClick={() => onSidebarInfoChange(null)}>关闭</button></section> : null}
      <nav className="mobile-product-nav" aria-label="Creative OS 导航">{productNav.map((item) => <button key={item.value} type="button" aria-current={surface === item.value ? 'page' : undefined} onClick={() => onNavigateSurface(item.value)} className={surface === item.value ? 'is-active' : ''}>{item.icon}<span>{item.label}</span></button>)}</nav>
      {projectContext}
      <main id="main-content"><ErrorBoundary resetKeys={errorResetKeys} onBack={onErrorBack} backLabel="返回制作页">{children}</ErrorBoundary></main>
    </div>
    <nav className="mobile-nav" aria-label="移动端主导航" style={{ gridTemplateColumns: `repeat(${mobileNav.length}, minmax(0, 1fr))` }}>{mobileNav.map((item) => <button key={item.value} aria-current={view === item.value ? 'page' : undefined} onClick={() => onSwitchView(item.value)} className={view === item.value ? 'is-active' : ''}>{item.icon}<span>{item.label}</span>{item.badge ? <i>{item.badge}</i> : null}</button>)}</nav>
    {overlays}
  </div>
}
