/**
 * Job Radar dashboard panel for DSH settings page.
 * Reads job data through the jobRadar Remote (host plugin) and renders
 * filterable job cards with status marking — no separate server needed.
 */
import { createElement as h, useEffect, useMemo, useState } from 'react'

/** The remote namespace face as mounted by the host plugin. */
interface JobRadarFace {
  list(filter?: { grade?: string; status?: string; days?: number }): Promise<{ jobs: any[]; total: number }>
  stats(): Promise<Record<string, number>>
  setStatus(jid: string, status: string): Promise<{ ok: boolean; error?: string }>
}

interface PanelInjected {
  hooks: { remote: () => JobRadarFace | undefined }
}

const STATUS_LABEL: Record<string, string> = {
  new: '新发现',
  applied: '已投递',
  interested: '有意向',
  rejected: '已放弃',
}
const STATUS_COLOR: Record<string, string> = {
  new: '#3b82f6',
  applied: '#10b981',
  interested: '#f59e0b',
  rejected: '#ef4444',
}
const GRADE_COLOR: Record<string, string> = {
  S: '#10b981',
  A: '#3b82f6',
  B: '#f59e0b',
  C: '#94a3b8',
}

export function RadarPanel({ hooks }: PanelInjected): ReturnType<typeof createElement> {
  const [jobs, setJobs] = useState<any[]>([])
  const [stats, setStats] = useState<Record<string, number>>({})
  const [grade, setGrade] = useState<string>('')
  const [status, setStatus] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>('')

  const load = async (): Promise<void> => {
    const remote = hooks.remote()
    if (!remote) {
      setError('Job Radar 服务未挂载(dataDir 未配置)')
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const filter: any = {}
      if (grade) filter.grade = grade
      if (status) filter.status = status
      const [listRes, statsRes] = await Promise.all([remote.list(filter), remote.stats()])
      setJobs(listRes.jobs)
      setStats(statsRes)
      setError('')
    } catch (e: any) {
      setError('加载失败: ' + (e?.message ?? String(e)))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [grade, status])

  const mark = async (jid: string, st: string): Promise<void> => {
    const remote = hooks.remote()
    if (!remote) return
    const res = await remote.setStatus(jid, st)
    if (res.ok) void load()
    else setError('标记失败: ' + (res.error ?? ''))
  }

  const grades = ['S', 'A', 'B', 'C']
  const statuses = Object.keys(STATUS_LABEL)
  const total = stats.total ?? 0

  const cardStyle = {
    border: '1px solid #e2e8f0',
    borderRadius: 10,
    padding: '10px 14px',
    marginBottom: 8,
    background: '#fff',
  } as const
  const badgeStyle = (g: string) => ({
    display: 'inline-block',
    minWidth: 22,
    textAlign: 'center' as const,
    borderRadius: 6,
    padding: '1px 6px',
    marginRight: 8,
    fontWeight: 700,
    color: '#fff',
    background: GRADE_COLOR[g] ?? '#94a3b8',
  })
  const chipStyle = (active: boolean) => ({
    border: active ? '2px solid #3b82f6' : '1px solid #cbd5e1',
    borderRadius: 999,
    padding: '2px 10px',
    marginRight: 6,
    marginBottom: 6,
    cursor: 'pointer',
    background: active ? '#eff6ff' : '#fff',
    color: active ? '#1d4ed8' : '#475569',
    fontSize: 12,
  })

  return h('div', { style: { fontFamily: 'inherit' } }, [
    // Stats row
    h('div', { key: 'stats', style: { display: 'flex', gap: 12, marginBottom: 10, flexWrap: 'wrap' } }, [
      h('span', { key: 't', style: statChip('#334155') }, `总数 ${total}`),
      h('span', { key: 's', style: statChip(GRADE_COLOR.S) }, `S ${stats.grade_S ?? 0}`),
      h('span', { key: 'a', style: statChip(GRADE_COLOR.A) }, `A ${stats.grade_A ?? 0}`),
      h('span', { key: 'b', style: statChip(GRADE_COLOR.B) }, `B ${stats.grade_B ?? 0}`),
      h('span', { key: 'ap', style: statChip(STATUS_COLOR.applied) }, `已投 ${stats.status_applied ?? 0}`),
      h('button', { key: 'ref', onClick: () => void load(), style: refreshStyle() }, '🔄 刷新'),
    ]),
    // Grade filter
    h('div', { key: 'gf' }, [
      chip('', '全部等级', grade === ''),
      ...grades.map((g) => chip(g, `${g} 级`, grade === g)),
    ]),
    // Status filter
    h('div', { key: 'sf' }, [
      chip('', '全部状态', status === ''),
      ...statuses.map((s) => chip(s, STATUS_LABEL[s], status === s)),
    ]),
    error ? h('div', { key: 'err', style: { color: '#dc2626', margin: '8px 0' } }, error) : null,
    loading ? h('div', { key: 'ld', style: { color: '#64748b', margin: '16px 0' } }, '加载中...') : null,
    // Job cards
    h('div', { key: 'list' }, jobs.map((j) => h('div', { key: j.id, style: cardStyle }, [
      h('div', { key: 't', style: { fontWeight: 600, fontSize: 14 } }, [
        h('span', { key: 'b', style: badgeStyle(j.grade) }, j.grade ?? '?'),
        j.title || '(无标题)',
        j.url ? h('a', { key: 'l', href: j.url, target: '_blank', style: { marginLeft: 8, fontSize: 12, color: '#3b82f6' } }, '🔗') : null,
      ]),
      h('div', { key: 'm', style: { fontSize: 12, color: '#64748b', margin: '4px 0' } }, [
        `${j.company || '-'} · ${j.city || '-'} · ${fmtSalary(j)} · 评分 ${j.score ?? 0}`,
      ]),
      h('div', { key: 'a', style: { marginTop: 6 } }, [
        ...statuses.map((s) => h('button', {
          key: s,
          onClick: () => void mark(j.id, s),
          style: miniBtn(j.status === s, STATUS_COLOR[s]),
        }, STATUS_LABEL[s])),
      ]),
    ]))),
  ])

  function chip(value: string, label: string, active: boolean): ReturnType<typeof createElement> {
    return h('button', { key: value, onClick: () => (value === '' ? (grade === '' ? null : setGrade('')) : setGrade(value)), style: chipStyle(active) }, label)
  }
}

function statChip(color: string): Record<string, string> {
  return {
    border: '1px solid #e2e8f0',
    borderRadius: 8,
    padding: '4px 10px',
    background: '#f8fafc',
    color,
    fontWeight: 600,
    fontSize: 12,
  }
}

function refreshStyle(): Record<string, string> {
  return {
    marginLeft: 'auto',
    border: '1px solid #cbd5e1',
    borderRadius: 8,
    padding: '4px 10px',
    background: '#fff',
    cursor: 'pointer',
    fontSize: 12,
  }
}

function miniBtn(active: boolean, color: string): Record<string, string> {
  return {
    border: active ? `2px solid ${color}` : '1px solid #cbd5e1',
    borderRadius: 6,
    padding: '2px 8px',
    marginRight: 6,
    cursor: 'pointer',
    background: active ? color : '#fff',
    color: active ? '#fff' : '#475569',
    fontSize: 12,
  }
}

function fmtSalary(j: any): string {
  if (j.salary_min && j.salary_max) {
    return `${Math.round(j.salary_min / 1000)}-${Math.round(j.salary_max / 1000)}K`
  }
  return '面议'
}
