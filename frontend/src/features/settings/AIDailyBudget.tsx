import { AlertTriangle, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getAIQuota } from '../../api'
import type { AIQuota } from '../../types'
import { IconButton } from '../../shared/components/ui/Button'
import './aiDailyBudget.css'

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 3,
})

function money(value: string | undefined): string {
  if (value === undefined || !/^\d+(?:\.\d{1,3})?$/.test(value)) return '未提供'
  const amount = Number(value)
  return Number.isFinite(amount) ? usd.format(amount) : '未提供'
}

const entryLabels: Record<string, string> = {
  task_analysis: '方案分析',
  prompt_assistant: '提示词助手',
  image_submission: '图片生成',
  video_submission: '视频生成',
  feedback_learning: '反馈学习',
  director_planning: '导演规划',
  quality_review: '质量复核',
}

function entryNames(entries: string[]): string {
  return [...new Set(entries.map((entry) => entryLabels[entry] ?? '其他调用'))].join('、')
}

export function AIBudgetSummary({ quota }: { quota: AIQuota }) {
  const lowAvailable = money(quota.available) !== '未提供' && Number(quota.available) < 0.01
  const unknown = money(quota.unknown) !== '未提供' && Number(quota.unknown) > 0
  const historicalUnknown = money(quota.historical_unknown) !== '未提供' && Number(quota.historical_unknown) > 0
  const priceMissing = quota.diagnostics.pricing_configured === false || (quota.diagnostics.missing_price_entries?.length ?? 0) > 0
  const metrics = [
    ['total', '总额度', quota.total],
    ['available', '可用额度', quota.available],
    ['reserved', '处理中预占', quota.reserved],
    ['settled', '已结算', quota.settled],
    ['unknown', '待核实 (UNKNOWN)', quota.unknown],
  ] as const

  return <>
    <p className="ai-budget-date">额度日期 {quota.business_date} · 美元 USD</p>
    <dl className="ai-budget-values">
      {metrics.map(([key, label, value]) => <div key={key} data-budget-value={key}>
        <dt>{label}</dt><dd className={key === 'available' ? `ai-budget-available${lowAvailable ? ' is-low' : ''}` : undefined}>{money(value)}</dd>
      </div>)}
    </dl>
    <p className="ai-budget-limits">
      单次上限 {money(quota.request_max)} · 批次上限 {money(quota.batch_max)} · 未终结占用上限 {money(quota.pending_max)}
      {quota.pending_available !== undefined ? <> · 未终结可用 {money(quota.pending_available)}</> : null}
    </p>
    <div className="ai-budget-notices" role="status">
      {lowAvailable ? <p><AlertTriangle size={16} aria-hidden="true" />可用额度不足 $0.01，请等待占用结算或额度更新。</p> : null}
      {unknown || historicalUnknown ? <p><AlertTriangle size={16} aria-hidden="true" />有费用待核实；未核实的占用不会因跨日自动释放。</p> : null}
      {quota.legacy_reconciliation_required ? <p><AlertTriangle size={16} aria-hidden="true" />历史用额需核查，旧记录尚未换算为美元；新调用以服务端核查结果为准。</p> : null}
      {priceMissing ? <p><AlertTriangle size={16} aria-hidden="true" />部分价格未配置，无法确认这些调用的费用；新调用以服务端价格校验为准。</p> : null}
    </div>
    <div className="ai-budget-history">
      <span>历史处理中预占：{money(quota.historical_reserved)}</span>
      <span>历史待核实 (UNKNOWN)：{money(quota.historical_unknown)}</span>
    </div>
    <div className="ai-budget-categories" aria-label="分类用额">
      {(['text', 'image', 'video'] as const).map((category) => {
        const usage = quota.breakdown?.[category]
        const label = { text: '文字', image: '图片', video: '视频' }[category]
        return <div key={category}><strong>{label}</strong><span>{usage
          ? `处理中 ${money(usage.reserved)} · 已结算 ${money(usage.settled)} · 待核实 ${money(usage.unknown)}`
          : '暂无分类用额数据'}</span></div>
      })}
    </div>
    <p className="ai-budget-scope">已接入额度控制：{entryNames(quota.enforced_entries) || '未提供'}。
      {quota.deferred_entries.length > 0 ? <> 尚未接入：{entryNames(quota.deferred_entries)}。</> : null}
      {!priceMissing && quota.diagnostics.pricing_configured === undefined ? <> 价格配置状态未提供。</> : null}
    </p>
  </>
}

type BudgetState = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; quota: AIQuota }

export function AIDailyBudget() {
  const [state, setState] = useState<BudgetState>({ status: 'loading' })
  const pending = useRef<AbortController | null>(null)
  const load = useCallback(async () => {
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setState({ status: 'loading' })
    try {
      const quota = await getAIQuota(controller.signal)
      if (controller.signal.aborted) return
      if (quota.currency !== 'USD') throw new Error('Unsupported quota currency')
      setState({ status: 'ready', quota })
    } catch (cause) {
      if (controller.signal.aborted) return
      setState({
        status: 'error',
        message: cause instanceof ApiError ? cause.message : '无法读取 AI 每日额度，请刷新重试。',
      })
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => {
      window.clearTimeout(timer)
      pending.current?.abort()
    }
  }, [load])

  return <section className="settings-section ai-daily-budget" aria-labelledby="ai-daily-budget-heading" aria-busy={state.status === 'loading'}>
    <div className="settings-section-heading">
      <div><h2 id="ai-daily-budget-heading">AI 每日额度</h2><p>当前账号的共享美元额度，处理中和待核实费用保留占用。</p></div>
      <IconButton label={state.status === 'error' ? '重试读取 AI 每日额度' : '刷新 AI 每日额度'} disabled={state.status === 'loading'} onClick={() => void load()}>
        <RefreshCw size={17} aria-hidden="true" />
      </IconButton>
    </div>
    {state.status === 'loading' ? <p className="ai-budget-loading" role="status">正在读取 AI 每日额度…</p> : null}
    {state.status === 'error' ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} aria-hidden="true" />{state.message}</div> : null}
    {state.status === 'ready' ? <AIBudgetSummary quota={state.quota} /> : null}
  </section>
}
