import { AlertTriangle, ArrowLeft, RefreshCw } from 'lucide-react'
import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { haveResetKeysChanged } from './errorBoundaryReset'
import type { ErrorBoundaryResetKey } from './errorBoundaryReset'

type ErrorBoundaryProps = {
  children: ReactNode
  resetKeys?: readonly ErrorBoundaryResetKey[]
  onBack?: () => void
  backLabel?: string
  fullPage?: boolean
}

type ErrorBoundaryState = {
  error: Error | null
}

export function ErrorFallback({
  onRetry,
  onBack,
  backLabel = '返回上一页',
  fullPage = false,
}: {
  onRetry: () => void
  onBack?: () => void
  backLabel?: string
  fullPage?: boolean
}) {
  const Heading = fullPage ? 'h1' : 'h2'
  return <div className={`error-fallback${fullPage ? ' error-fallback--full-page' : ''}`} role="alert">
    <span className="error-fallback__icon"><AlertTriangle size={24} /></span>
    <div>
      <Heading>{fullPage ? '页面暂时无法打开' : '此页面暂时无法显示'}</Heading>
      <p>页面运行时遇到异常，其他数据和任务不会受到影响。你可以重试，或返回后继续操作。</p>
    </div>
    <div className="error-fallback__actions">
      <button className="primary-button" type="button" onClick={onRetry}><RefreshCw size={16} />重试</button>
      {onBack ? <button className="secondary-button" type="button" onClick={onBack}><ArrowLeft size={16} />{backLabel}</button> : null}
    </div>
  </div>
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('React page error boundary caught an error', error, info.componentStack)
  }

  componentDidUpdate(previousProps: ErrorBoundaryProps) {
    if (this.state.error && haveResetKeysChanged(previousProps.resetKeys, this.props.resetKeys)) {
      this.setState({ error: null })
    }
  }

  private retry = () => this.setState({ error: null })

  render() {
    if (this.state.error) {
      return <ErrorFallback
        onRetry={this.retry}
        onBack={this.props.onBack}
        backLabel={this.props.backLabel}
        fullPage={this.props.fullPage}
      />
    }
    return this.props.children
  }
}
