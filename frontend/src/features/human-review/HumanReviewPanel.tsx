import { Download, LoaderCircle, RefreshCw, Save } from 'lucide-react'
import { useId, useRef, useState } from 'react'
import { ApiError, getHumanReviewExport, getHumanReviewHistory, submitHumanReview } from '../../api'
import { createUuid } from '../../uuid'
import type { HumanReviewHistory, HumanReviewInput, HumanReviewQuery, HumanReviewReason, HumanReviewVerdict } from './contracts'
import { humanReviewInputError, humanReviewReasons, persistPendingHumanReview, readPendingHumanReview } from './humanReviewModel'
import './humanReview.css'

export function HumanReviewPanel(props: HumanReviewQuery & { canWrite?: boolean }) {
  return <HumanReviewForm key={`${props.subjectType}:${props.taskId ?? ''}:${props.subjectId}`} {...props} />
}

function HumanReviewForm({ canWrite = true, ...query }: HumanReviewQuery & { canWrite?: boolean }) {
  const [pending, setPending] = useState(() => readPendingHumanReview(query))
  const [verdict, setVerdict] = useState<HumanReviewVerdict>(pending?.verdict ?? 'PASS')
  const [reasons, setReasons] = useState<HumanReviewReason[]>(pending?.reasonCodes ?? [])
  const [note, setNote] = useState(pending?.note ?? '')
  const [history, setHistory] = useState<HumanReviewHistory | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(pending ? '上次保存结果待确认' : '')
  const loadingRef = useRef(false)
  const submitting = useRef(false)
  const name = useId()
  const input: HumanReviewInput = {
    ...query, reviewKey: '', expectedOutputHash: history?.subject.outputHash ?? '',
    verdict, reasonCodes: reasons, note: note.trim(),
  }
  const validation = humanReviewInputError(input)
  const clearPending = () => {
    persistPendingHumanReview(query, null)
    setPending(null)
  }
  async function load() {
    if (loadingRef.current) return
    loadingRef.current = true
    setLoading(true)
    try {
      const data = await getHumanReviewHistory(query)
      setHistory(data)
      if (pending && data.reviews.some(review => review.reviewKey === pending.reviewKey)) {
        clearPending()
        setNotice('已确认上次评价已记录')
      } else {
        setNotice(pending ? '上次结果待确认，可重试同一评价' : '')
      }
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '评价历史读取失败')
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }
  async function save() {
    if (submitting.current || loadingRef.current || !canWrite || !history || (!pending && validation)) return
    const request = pending ?? { ...input, reviewKey: createUuid(), reasonCodes: [...new Set(reasons)].sort() }
    if (!persistPendingHumanReview(query, request)) {
      setNotice('恢复信息无法保存，评价未提交')
      return
    }
    submitting.current = true
    setPending(request)
    setBusy(true)
    setNotice('')
    try {
      const review = await submitHumanReview(request)
      clearPending()
      setHistory(current => current ? { ...current, reviews: [review, ...current.reviews.filter(item => item.id !== review.id)] } : current)
      setNotice('已记录人工评价')
    } catch (cause) {
      const unknown = !(cause instanceof ApiError) || cause.status >= 500 || cause.status === 408 || cause.code.includes('IN_PROGRESS')
      if (!unknown) clearPending()
      setNotice(unknown ? '保存结果待确认，请核对历史或重试同一评价' : cause.message)
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }
  async function download() {
    try {
      const data = await getHumanReviewExport(query)
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `human-reviews-${query.subjectId.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setNotice(data.records.length ? '已导出评价数据' : '暂无真实评价数据')
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '评价数据导出失败')
    }
  }
  return <details className="human-review" onToggle={event => { if (event.currentTarget.open && !history) void load() }}>
    <summary>人工生产评价</summary>
    <p className="human-review__scope">{history?.subject.synthetic ? '离线记录 · 默认排除训练导出' : '人工评价记录'} · 合格与交付审核独立</p>
    <div className="human-review__tools">
      <button type="button" title="刷新评价历史" aria-label="刷新评价历史" disabled={loading || busy} onClick={() => void load()}>{loading ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />}</button>
      <button type="button" title="下载评价数据" aria-label="下载评价数据" disabled={!history || busy} onClick={() => void download()}><Download size={16} /></button>
    </div>
    {history ? <>
      <fieldset disabled={!canWrite || busy || Boolean(pending)}>
        <legend>评价结论</legend>
        <div className="human-review__choices">
          {(query.subjectType === 'VIDEO_VARIANT' ? ['PASS', 'FAIL'] as const : ['PASS', 'REWORK', 'FAIL'] as const).map(value => <label key={value}><input type="radio" name={name} checked={verdict === value} onChange={() => { setVerdict(value); if (value === 'PASS') setReasons([]) }} />{value}</label>)}
        </div>
        {verdict !== 'PASS' ? <div className="human-review__reasons">
          {humanReviewReasons(query.subjectType).map(([code, label]) => <label key={code}><input type="checkbox" checked={reasons.includes(code)} onChange={event => setReasons(current => event.target.checked ? [...current, code] : current.filter(item => item !== code))} />{code} · {label}</label>)}
        </div> : null}
        <label className="human-review__note"><span>说明{reasons.includes('OTHER') ? '（必填）' : ''}</span><textarea value={note} maxLength={255} rows={2} onChange={event => setNote(event.target.value)} /></label>
      </fieldset>
      <div className="human-review__tools">
        <button type="button" title={pending ? '重试同一评价' : '保存人工评价'} aria-label={pending ? '重试同一评价' : '保存人工评价'} disabled={!canWrite || busy || loading || (!pending && Boolean(validation))} onClick={() => void save()}>{busy ? <LoaderCircle size={16} className="spin" /> : pending ? <RefreshCw size={16} /> : <Save size={16} />}</button>
        {validation && !pending ? <small>{validation}</small> : null}
      </div>
      {history.reviews.length ? <ol className="human-review__history" aria-label="人工评价历史">
        {[...history.reviews].sort((left, right) => right.reviewedAt.localeCompare(left.reviewedAt) || right.id.localeCompare(left.id)).map(review => <li key={review.id}><strong>{review.verdict}</strong><span>{review.reasonCodes.join(' · ')}</span>{review.note ? <p>{review.note}</p> : null}<small>{review.reviewedAt} · {review.reviewerId}</small></li>)}
      </ol> : <p className="human-review__empty">暂无人工评价</p>}
    </> : null}
    <p role="status" aria-live="polite">{notice}</p>
  </details>
}
