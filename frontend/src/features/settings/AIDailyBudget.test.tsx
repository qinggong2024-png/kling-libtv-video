import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { AIQuota } from '../../types'
import { AIBudgetSummary } from './AIDailyBudget'

const quota: AIQuota = {
  currency: 'USD', business_date: '2026-10-14', accounting_version: 'USD_V1',
  total: '50.000', available: '39.000', reserved: '3.000', settled: '6.000', unknown: '2.000',
  request_max: '5.000', batch_max: '10.000', legacy_reconciliation_required: false,
  diagnostics: { total_units: 50000 }, enforced_entries: ['task_analysis', 'prompt_assistant'],
  deferred_entries: ['image_submission', 'video_submission'],
}

describe('Dollar budget evidence presentation', () => {
  it('displays five dollar values and never exposes diagnostic units', () => {
    const html = renderToStaticMarkup(<AIBudgetSummary quota={quota} />)
    for (const amount of ['$50.00', '$39.00', '$3.00', '$6.00', '$2.00']) expect(html).toContain(amount)
    expect(html).not.toContain('50000')
    expect(html).toContain('尚未接入')
  })

  it('retains sub-cent precision and warns on low availability', () => {
    const html = renderToStaticMarkup(<AIBudgetSummary quota={{ ...quota, available: '0.001' }} />)
    expect(html).toContain('$0.001')
    expect(html).toContain('可用额度不足')
  })

  it('does not invent missing categories, pending limits, or historical amounts', () => {
    const html = renderToStaticMarkup(<AIBudgetSummary quota={quota} />)
    expect(html.match(/暂无分类用额数据/g)).toHaveLength(3)
    expect(html).toContain('未终结占用上限 未提供')
    expect(html).toContain('历史待核实 (UNKNOWN)：未提供')
  })

  it('shows genuine categories, historical unknown, reconciliation and missing prices', () => {
    const html = renderToStaticMarkup(<AIBudgetSummary quota={{
      ...quota, unknown: '0.000', historical_unknown: '1.234', historical_reserved: '0.500',
      pending_max: '10.000', pending_available: '8.266', legacy_reconciliation_required: true,
      diagnostics: { pricing_configured: false },
      breakdown: { text: { reserved: '0.000', settled: '0.005' } },
    }} />)
    expect(html).toContain('$1.234')
    expect(html).toContain('$0.005')
    expect(html).toContain('待核实 未提供')
    expect(html).toContain('不会因跨日自动释放')
    expect(html).toContain('历史用额需核查')
    expect(html).toContain('部分价格未配置')
  })

  it('does not turn malformed money into zero', () => {
    const html = renderToStaticMarkup(<AIBudgetSummary quota={{ ...quota, available: '' }} />)
    expect(html).toMatch(/data-budget-value="available".*?未提供/)
    expect(html).not.toContain('可用额度不足')
  })
})
