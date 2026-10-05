// 状态机契约同步测试（2026-09-21 前端架构拆分 v1 新增）。
//
// 存在理由：2026-09-21 发生过 AWAITING_FINAL_APPROVAL 漏映射事故 —— 后端新增 phase、
// 前端 statusMeta 没跟上，UI 直接外泄裸枚举。当时靠人工评审才发现。
// 现在把「每个 phase 必须有中文标签且有语义归属」变成断言，让同类事故在 CI/test 阶段就失败。
//
// 数据源是后端契约本身（backend/contracts/state-machines.json），不是前端自说自话，
// 因此后端加 phase 而前端不改时，这里必然红。
import { describe, expect, it } from 'vitest'
import contractJson from '../../../backend/contracts/state-machines.json'
import {
  ACTIVE_PHASES,
  ATTEMPT_STATUS_META,
  CLASSIFIED_PHASES,
  CONTRACT_UNREACHABLE_PHASES,
  SETTLED_PHASES,
  TASK_PHASE_META,
  statusMeta,
} from './workflowStates'

type Contract = {
  parentTask: { initial: string; terminal: string[]; restingStates: string[]; transitions: Record<string, string[]> }
  reconciliation: { aggregateOutputs: string[]; reservedPhases: Record<string, string> }
}

const contract = contractJson as unknown as Contract
const contractPhases = Object.keys(contract.parentTask.transitions)

describe('状态机契约同步', () => {
  it('契约确实被读到了（防止路径写错导致测试空跑）', () => {
    expect(contractPhases.length).toBeGreaterThanOrEqual(14)
    expect(contract.parentTask.initial).toBe('DRAFT')
  })

  it('契约里每个 parentTask phase 都有中文标签映射', () => {
    const missing = contractPhases.filter((phase) => !(phase in TASK_PHASE_META))
    expect(missing).toEqual([])
  })

  it('TASK_PHASE_META 不含契约之外的 phase（防止前端自造状态）', () => {
    const extra = Object.keys(TASK_PHASE_META).filter((phase) => !contractPhases.includes(phase))
    expect(extra).toEqual([])
  })

  it('每个 phase 都有语义归属，不存在无归属 phase', () => {
    const unclassified = contractPhases.filter((phase) => !CLASSIFIED_PHASES.has(phase))
    expect(unclassified).toEqual([])
  })

  it('契约标记为 design-intent-only 的 phase：前端已登记，且从 initial 不可达', () => {
    // 与契约 reconciliation.reservedPhases 逐字对齐（改名/增删都会在这里红）。
    const reserved = Object.keys(contract.reconciliation.reservedPhases).sort()
    expect(reserved).toEqual([...CONTRACT_UNREACHABLE_PHASES].sort())

    // 硬证据：从 initial 做转移闭包，保留 phase 必须落不进去。
    // 注意不能简单断言「没有边指向它们」—— VALIDATING 确实有一条入边（来自 DOWNLOADING），
    // 但 DOWNLOADING 自身不可达，所以 VALIDATING 依然不可达。可达性只能靠闭包判定。
    const reachable = new Set<string>([contract.parentTask.initial])
    const queue = [contract.parentTask.initial]
    while (queue.length > 0) {
      const current = queue.shift() as string
      for (const next of contract.parentTask.transitions[current] ?? []) {
        if (!reachable.has(next)) {
          reachable.add(next)
          queue.push(next)
        }
      }
    }

    for (const phase of CONTRACT_UNREACHABLE_PHASES) {
      expect(reachable.has(phase)).toBe(false)
      // 聚合层也永不产出。
      expect(contract.reconciliation.aggregateOutputs).not.toContain(phase)
      // 不是停表态 → 计时器不能因它们停下。
      expect(SETTLED_PHASES.has(phase)).toBe(false)
      // ★ 但仍保留在 ACTIVE_PHASES 内，这是**有意的**：它们按设计意图属于「在途」，
      //   若后端将来真的实现，轮询/计时逻辑无需改动即可继续工作。
      //   （若哪天要摘掉，需同时改 workflowStates.ts 的注释与本节断言。）
      expect(ACTIVE_PHASES.has(phase)).toBe(true)
    }

    // 可达闭包自身健全性：终态可达、design-intent-only 之外的所有 phase 都可达。
    expect(reachable.has('DELIVERABLE')).toBe(true)
    expect(reachable.has('ACTION_REQUIRED')).toBe(true)
    const unreachableExceptReserved = contractPhases.filter(
      (phase) => !reachable.has(phase) && !CONTRACT_UNREACHABLE_PHASES.has(phase),
    )
    expect(unreachableExceptReserved).toEqual([])
  })

  it('SETTLED_PHASES 不是后端 terminal 的等价物', () => {
    // 契约只承认 CANCELLED 是终态；DELIVERABLE / ACTION_REQUIRED 是 resting，仍可被聚合移走。
    expect(contract.parentTask.terminal).toEqual(['CANCELLED'])
    expect(contract.parentTask.restingStates).toEqual(['DELIVERABLE', 'ACTION_REQUIRED'])
    expect(SETTLED_PHASES.has('CANCELLED')).toBe(true)
    expect(SETTLED_PHASES.size).toBeGreaterThan(contract.parentTask.terminal.length)
  })

  it('attempt / variant 状态不与 task phase 混表', () => {
    const attemptKeys = Object.keys(ATTEMPT_STATUS_META)
    expect(attemptKeys.length).toBeGreaterThan(0)
    for (const key of attemptKeys) {
      expect(contractPhases).not.toContain(key)
      expect(key in TASK_PHASE_META).toBe(false)
    }
  })

  it('合并查表可同时解析 phase 与 attempt 状态', () => {
    expect(statusMeta.DELIVERABLE).toEqual({ label: '已完成', tone: 'success' })
    expect(statusMeta.SUCCEEDED).toEqual({ label: '已完成', tone: 'success' })
    expect(statusMeta.ACTION_REQUIRED.tone).toBe('danger')
    expect(statusMeta.NOT_A_REAL_STATUS).toBeUndefined()
  })

  it('契约声明的聚合可达输出与已知边一致（契约漂移哨兵）', () => {
    expect(contract.reconciliation.aggregateOutputs).toEqual([
      'GENERATING',
      'AWAITING_FINAL_APPROVAL',
      'PARTIALLY_DELIVERABLE',
      'DELIVERABLE',
      'ACTION_REQUIRED',
    ])
    for (const phase of contract.reconciliation.aggregateOutputs) {
      expect(TASK_PHASE_META[phase]).toBeDefined()
      expect(CLASSIFIED_PHASES.has(phase)).toBe(true)
    }
  })
})
