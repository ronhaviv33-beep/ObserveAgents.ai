import { Fragment, useState, useEffect, useMemo } from 'react'
import { Bot, Wrench, Server, Zap, Globe, Database, ClipboardList, Table2, Cloud, Cpu, Shield, HelpCircle } from 'lucide-react'
import { fetchRelationships } from '../api.js'
import { relationshipEvidenceLabel } from '../discoveryStatus.js'
import { useBreakpoint } from '../hooks/useBreakpoint.js'
import CollapsiblePanel from '../components/CollapsiblePanel.jsx'

// ── Design tokens ──────────────────────────────────────────────────────────────
const T = {
  bg:       '#F8FAFC',
  panel:    '#FFFFFF',
  panelHi:  '#F1F5F9',
  border:   '#E2E8F0',
  borderHi: '#CBD5E1',
  text:     '#0F172A',
  textDim:  '#475569',
  textMute: '#64748B',
  accent:   '#2563EB',
  success:  '#16A34A',
  warn:     '#D97706',
  crit:     '#DC2626',
  purple:   '#7C3AED',
  teal:     '#0D9488',
  info:     '#0891B2',
}
const FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"
const FONT_SANS = "'Inter', system-ui, sans-serif"

// ── Type colours & icons ──────────────────────────────────────────────────────
const TYPE_META = {
  agent:      { color: T.accent,   icon: '🤖', label: 'Agent',      Icon: Bot },
  mcp_tool:   { color: T.teal,     icon: '🔧', label: 'MCP Tool',   Icon: Wrench },
  mcp_server: { color: T.purple,   icon: '🖧',  label: 'MCP Server', Icon: Server },
  workflow:   { color: T.warn,     icon: '⚡', label: 'Workflow',   Icon: Zap },
  api:        { color: T.info,     icon: '🌐', label: 'API',        Icon: Globe },
  database:   { color: T.success,  icon: '🗄',  label: 'Database',   Icon: Database },
  crm:        { color: '#EA580C',  icon: '📋', label: 'CRM',        Icon: ClipboardList },
  spreadsheet:{ color: '#16A34A',  icon: '📊', label: 'Spreadsheet', Icon: Table2 },
  provider:   { color: T.accent,   icon: '◈',  label: 'Provider',   Icon: Cloud },
  model:      { color: T.purple,   icon: '⊞',  label: 'Model',      Icon: Cpu },
  gateway:    { color: T.success,  icon: '⊕',  label: 'Gateway',    Icon: Shield },
  unknown:    { color: T.textMute, icon: '?',  label: 'Unknown',    Icon: HelpCircle },
}

const REL_META = {
  calls:            { color: T.info,    label: 'calls' },
  uses_tool:        { color: T.teal,    label: 'uses tool' },
  invokes_workflow: { color: T.warn,    label: 'triggers workflow' },
  triggers:         { color: T.warn,    label: 'triggers' },
  writes_to:        { color: T.crit,    label: 'writes to' },
  reads_from:       { color: T.success, label: 'reads from' },
  sends_event_to:   { color: T.purple,  label: 'sends event to' },
  uses_provider:    { color: T.accent,  label: 'uses provider' },
  uses_model:       { color: T.purple,  label: 'uses model' },
  routes_via:       { color: T.success, label: 'routes via' },
}

const TARGET_TYPE_OPTIONS = [
  { value: '',           label: 'All types' },
  { value: 'provider',  label: 'Provider' },
  { value: 'model',     label: 'Model' },
  { value: 'gateway',   label: 'Gateway' },
  { value: 'mcp_tool',  label: 'MCP Tool' },
  { value: 'mcp_server',label: 'MCP Server' },
  { value: 'workflow',  label: 'Workflow' },
  { value: 'api',       label: 'API' },
  { value: 'database',  label: 'Database' },
  { value: 'crm',       label: 'CRM' },
  { value: 'spreadsheet', label: 'Spreadsheet' },
  { value: 'unknown',   label: 'Unknown' },
]

const REL_TYPE_OPTIONS = [
  { value: '',                label: 'All relationships' },
  { value: 'uses_provider',   label: 'uses provider' },
  { value: 'uses_model',      label: 'uses model' },
  { value: 'routes_via',      label: 'routes via' },
  { value: 'calls',           label: 'calls' },
  { value: 'uses_tool',       label: 'uses tool' },
  { value: 'invokes_workflow',label: 'invokes workflow' },
  { value: 'triggers',        label: 'triggers' },
  { value: 'writes_to',       label: 'writes to' },
  { value: 'reads_from',      label: 'reads from' },
  { value: 'sends_event_to',  label: 'sends event to' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtDate(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const now = Date.now()
    const diff = now - d.getTime()
    if (diff < 60000)  return 'just now'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
    return d.toLocaleDateString("en-US")
  } catch { return iso }
}

function TypeBadge({ type }) {
  const m = TYPE_META[type] || TYPE_META.unknown
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 3,
      fontSize: 10, fontFamily: FONT_MONO, letterSpacing: '0.06em', textTransform: 'uppercase',
      background: `${m.color}18`, color: m.color, border: `1px solid ${m.color}33`,
    }}>
      {m.icon} {m.label}
    </span>
  )
}

function RelBadge({ type }) {
  const m = REL_META[type] || { color: T.textDim, label: type }
  return (
    <span style={{
      padding: '2px 7px', borderRadius: 3,
      fontSize: 10, fontFamily: FONT_MONO, letterSpacing: '0.06em',
      background: `${m.color}18`, color: m.color, border: `1px solid ${m.color}33`,
    }}>
      {m.label}
    </span>
  )
}

function StrengthBadge({ rel }) {
  const ev = relationshipEvidenceLabel(rel)
  return (
    <span title={ev.why}
      style={{ padding: '2px 8px', borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO,
        background: `${ev.color}18`, color: ev.color, border: `1px solid ${ev.color}33`, whiteSpace: 'nowrap' }}>
      {ev.label}
    </span>
  )
}

// Fixed readability order for branches in a flow graph (gateway → provider → model first).
const REL_FLOW_ORDER = [
  'routes_via', 'uses_provider', 'uses_model', 'uses_tool',
  'reads_from', 'writes_to', 'calls', 'invokes_workflow', 'triggers', 'sends_event_to',
]
function relOrder(t) {
  const i = REL_FLOW_ORDER.indexOf(t)
  return i === -1 ? REL_FLOW_ORDER.length : i
}

// Coarsen an observation timestamp into a bucket so the same agent's flows at different
// times become distinct rows ("just now" vs "3h ago") without over-fragmenting old data.
function obsBucket(iso) {
  if (!iso) return 'unknown'
  const age = Date.now() - new Date(iso).getTime()
  if (Number.isNaN(age)) return 'unknown'
  if (age < 3600000)      return 'recent'                          // < 1h
  if (age < 86400000)     return 'h' + Math.floor(age / 3600000)   // hourly buckets within a day
  if (age < 604800000)    return 'd' + Math.floor(age / 86400000)  // daily buckets within a week
  return 'older'
}

// Group relationship rows into runtime observations. Honors trace/request/session ids if
// they ever appear in metadata (no invention); otherwise groups by source_agent + time bucket.
function groupRelationships(rows) {
  const groups = new Map()
  for (const r of rows) {
    const m = r.metadata || {}
    const key = m.trace_id || m.request_id || m.session_id
      || `${r.source_agent_name}__${obsBucket(r.last_seen_at)}`
    if (!groups.has(key)) groups.set(key, { key, sourceAgent: r.source_agent_name, rows: [] })
    groups.get(key).rows.push(r)
  }
  const out = []
  for (const g of groups.values()) {
    const lastSeen = g.rows.reduce((mx, r) => {
      const t = new Date(r.last_seen_at).getTime()
      return Number.isNaN(t) ? mx : Math.max(mx, t)
    }, 0)
    const targetTypes = [...new Set(g.rows.map(r => r.target_type))]
    const requests = g.rows.reduce((mx, r) => Math.max(mx, r.request_count || 0), 0)
    const strengths = [...new Set(g.rows.map(r => relationshipEvidenceLabel(r).label))]
    out.push({
      ...g,
      lastSeenMs: lastSeen,
      lastSeenIso: lastSeen ? new Date(lastSeen).toISOString() : g.rows[0]?.last_seen_at,
      relationshipCount: g.rows.length,
      targetTypes,
      requests,
      strengthSummary: strengths.join(' / '),
    })
  }
  return out.sort((a, b) => b.lastSeenMs - a.lastSeenMs)
}

function Select({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        background: T.panel, border: `1px solid ${T.border}`, color: T.text,
        padding: '6px 10px', borderRadius: 4, fontSize: 11, fontFamily: FONT_MONO,
        cursor: 'pointer', outline: 'none',
      }}
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function RelationshipMap() {
  const bp = useBreakpoint()
  const [rows, setRows]           = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)
  const [targetType, setTargetType]       = useState('')
  const [relType, setRelType]             = useState('')
  const [sourceFilter, setSourceFilter]   = useState('')
  const [viewMode, setViewMode]           = useState('flows')   // 'flows' | 'all'
  const [flowGroup, setFlowGroup]         = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchRelationships()
      .then(data => { setRows(data); setLoading(false) })
      .catch(e  => { setError(e.message); setLoading(false) })
  }, [])

  const filtered = useMemo(() => {
    return rows.filter(r => {
      if (targetType && r.target_type !== targetType) return false
      if (relType    && r.relationship_type !== relType) return false
      if (sourceFilter) {
        const q = sourceFilter.toLowerCase()
        if (!r.source_agent_name.toLowerCase().includes(q)) return false
      }
      return true
    })
  }, [rows, targetType, relType, sourceFilter])

  const sourceAgents = useMemo(() => {
    const s = new Set(rows.map(r => r.source_agent_name))
    return Array.from(s).sort()
  }, [rows])

  const flowGroups = useMemo(() => groupRelationships(filtered), [filtered])

  return (
    <div style={{ background: T.bg, minHeight: '100vh', padding: bp.isMobile ? 0 : bp.isTablet ? 12 : 24, fontFamily: FONT_SANS }}>

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 11, fontFamily: FONT_MONO, letterSpacing: '0.14em', textTransform: 'uppercase', color: T.textMute, marginBottom: 6 }}>
          ObserveAgents · Runtime Dependency Map
        </div>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600, color: T.text }}>
          Runtime Dependency Map
        </h1>
        <p style={{ margin: '6px 0 0', fontSize: 13, color: T.textDim, maxWidth: 600 }}>
          We don't only discover AI agents. We map what they touch — every MCP server, tool, workflow, API, database, and CRM they interact with at runtime.
        </p>
      </div>

      {/* Field legend */}
      <div style={{ marginBottom: 20 }}>
        <CollapsiblePanel title="How to read this map" defaultExpanded={false}
          storageKey="oa-panel-deps-legend" subtitle="What each field in the dependency data means">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
            {[
              { label: 'Source Agent',     desc: 'The AI agent that initiated the interaction' },
              { label: 'Target System',    desc: 'MCP tool, server, API, database, CRM, or workflow called' },
              { label: 'Relationship Type',desc: 'How the agent interacts — calls, uses_tool, writes_to…' },
              { label: 'Evidence Source',  desc: 'What signal proved this link — gateway, mcp_headers, sdk…' },
              { label: 'Strength',         desc: 'How strong the evidence is for this relationship — Strong, Likely, Observed, or Partial' },
              { label: 'Last Seen',        desc: 'When this interaction was last observed in live traffic' },
              { label: 'Request Count',    desc: 'Total times this agent-to-target link has been observed' },
            ].map(({ label, desc }) => (
              <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 10, fontFamily: FONT_MONO, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.accent, fontWeight: 600 }}>{label}</span>
                <span style={{ fontSize: 11, color: T.textDim, lineHeight: 1.5 }}>{desc}</span>
              </div>
            ))}
          </div>
        </CollapsiblePanel>
      </div>

      {/* Filters */}
      <div style={{
        display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center',
        marginBottom: 20, padding: '14px 16px',
        background: T.panel, border: `1px solid ${T.border}`, borderRadius: 6,
      }}>
        <span style={{ fontSize: 10, fontFamily: FONT_MONO, letterSpacing: '0.1em', textTransform: 'uppercase', color: T.textMute }}>
          Filter
        </span>
        <input
          placeholder="Source agent…"
          value={sourceFilter}
          onChange={e => setSourceFilter(e.target.value)}
          style={{
            background: T.bg, border: `1px solid ${T.border}`, color: T.text,
            padding: '6px 10px', borderRadius: 4, fontSize: 11, fontFamily: FONT_MONO,
            outline: 'none', width: bp.isMobile ? '100%' : 180,
          }}
        />
        <Select value={targetType} onChange={setTargetType} options={TARGET_TYPE_OPTIONS} />
        <Select value={relType}    onChange={setRelType}    options={REL_TYPE_OPTIONS} />
        {(targetType || relType || sourceFilter) && (
          <button
            onClick={() => { setTargetType(''); setRelType(''); setSourceFilter('') }}
            style={{
              background: 'transparent', border: `1px solid ${T.border}`, color: T.textDim,
              padding: '5px 12px', borderRadius: 4, fontSize: 10, fontFamily: FONT_MONO,
              cursor: 'pointer', letterSpacing: '0.08em', textTransform: 'uppercase',
            }}
          >
            Clear
          </button>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, fontFamily: FONT_MONO, color: T.textMute }}>
          {filtered.length} of {rows.length} relationships
        </span>
      </div>

      {/* View toggle */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 16, background: T.panel, border: `1px solid ${T.border}`, borderRadius: 6, padding: 3, width: 'fit-content' }}>
        {[
          { id: 'flows', label: 'Runtime Flows' },
          { id: 'all',   label: 'All Relationships' },
        ].map(t => (
          <button key={t.id} onClick={() => setViewMode(t.id)}
            style={{
              background: viewMode === t.id ? T.panelHi : 'transparent',
              border: viewMode === t.id ? `1px solid ${T.border}` : '1px solid transparent',
              color: viewMode === t.id ? T.text : T.textDim,
              padding: '7px 16px', borderRadius: 4, fontSize: 11, fontFamily: FONT_MONO, cursor: 'pointer',
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: T.textMute, fontFamily: FONT_MONO, fontSize: 12 }}>
          Loading relationships…
        </div>
      ) : error ? (
        <div style={{ textAlign: 'center', padding: 60, color: T.crit, fontFamily: FONT_MONO, fontSize: 12 }}>
          Error: {error}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState />
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: T.textMute, fontFamily: FONT_MONO, fontSize: 12 }}>
          No relationships match the current filters.
        </div>
      ) : viewMode === 'flows' ? (
        <FlowSummaryTable groups={flowGroups} onViewFlow={setFlowGroup} />
      ) : (
        <RelationshipTable rows={filtered} />
      )}

      {flowGroup && <FlowModal group={flowGroup} onClose={() => setFlowGroup(null)} />}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div style={{
      background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8,
      padding: '48px 32px', textAlign: 'center',
    }}>
      <div style={{ fontSize: 36, marginBottom: 16 }}>🔗</div>
      <div style={{ fontSize: 16, fontWeight: 600, color: T.text, marginBottom: 8 }}>
        No external tool dependencies detected yet
      </div>
      <div style={{ fontSize: 13, color: T.textDim, maxWidth: 560, margin: '0 auto 6px', lineHeight: 1.6 }}>
        Provider and model relationships appear automatically once traffic flows.
        MCP relationships appear when tool metadata is observed.
      </div>
      <div style={{ fontSize: 13, color: T.textMute, maxWidth: 560, margin: '0 auto', lineHeight: 1.6 }}>
        Tool, MCP, database, and API links appear automatically from OpenTelemetry span attributes —
        no extra instrumentation needed.
      </div>
    </div>
  )
}

// ── Table ─────────────────────────────────────────────────────────────────────
const HEADERS = [
  'Source Agent', 'Relationship Type', 'Target Type', 'Target System', 'Evidence Source', 'Strength', 'Request Count', 'Last Seen',
]

function RelationshipTable({ rows }) {
  const [expanded, setExpanded] = useState(null)

  return (
    <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 6, overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            {HEADERS.map(h => (
              <th key={h} style={{
                padding: '10px 14px', textAlign: 'left',
                fontSize: 10, fontFamily: FONT_MONO, letterSpacing: '0.1em',
                textTransform: 'uppercase', color: T.textMute, fontWeight: 500,
                whiteSpace: 'nowrap',
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isOpen = expanded === r.id
            return [
              <tr
                key={r.id}
                onClick={() => setExpanded(isOpen ? null : r.id)}
                style={{
                  borderBottom: `1px solid ${T.border}`,
                  background: isOpen ? T.panelHi : i % 2 === 0 ? 'transparent' : `${T.bg}66`,
                  cursor: 'pointer',
                  transition: 'background 0.12s',
                }}
              >
                <td style={{ padding: '12px 14px' }}>
                  <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: T.text, fontWeight: 500 }}>
                    {r.source_agent_name}
                  </div>
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <RelBadge type={r.relationship_type} />
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <TypeBadge type={r.target_type} />
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: T.text }}>{r.target_name}</div>
                  {r.target_identifier && (
                    <div style={{ fontFamily: FONT_MONO, fontSize: 10, color: T.textMute, marginTop: 2 }}>
                      {r.target_identifier}
                    </div>
                  )}
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <span style={{ fontFamily: FONT_MONO, fontSize: 10, color: T.textDim }}>
                    {r.evidence_source}
                  </span>
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <StrengthBadge rel={r} />
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: T.text }}>
                    {r.request_count.toLocaleString()}
                  </span>
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <span style={{ fontFamily: FONT_MONO, fontSize: 11, color: T.textDim }}>
                    {fmtDate(r.last_seen_at)}
                  </span>
                </td>
              </tr>,
              isOpen && r.metadata && Object.keys(r.metadata).length > 0 && (
                <tr key={`${r.id}-detail`} style={{ background: T.panelHi, borderBottom: `1px solid ${T.border}` }}>
                  <td colSpan={HEADERS.length} style={{ padding: '10px 14px 14px 14px' }}>
                    <div style={{ fontSize: 10, fontFamily: FONT_MONO, letterSpacing: '0.1em', textTransform: 'uppercase', color: T.textMute, marginBottom: 8 }}>
                      Metadata
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 20px' }}>
                      {Object.entries(r.metadata).map(([k, v]) => (
                        <div key={k} style={{ fontFamily: FONT_MONO, fontSize: 11 }}>
                          <span style={{ color: T.textMute }}>{k}: </span>
                          <span style={{ color: T.textDim }}>{String(v)}</span>
                        </div>
                      ))}
                    </div>
                    <div style={{ display: 'flex', gap: 20, marginTop: 10, fontSize: 11, fontFamily: FONT_MONO, color: T.textMute }}>
                      <span>First seen: {fmtDate(r.first_seen_at)}</span>
                    </div>
                  </td>
                </tr>
              ),
            ]
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Grouped runtime-flow summary table ──────────────────────────────────────────
const FLOW_HEADERS = ['Source Agent', 'Last Seen', 'Relationships', 'Targets', 'Requests', 'Strength', '']

function FlowSummaryTable({ groups, onViewFlow }) {
  return (
    <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 6, overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 600 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            {FLOW_HEADERS.map((h, i) => (
              <th key={h || i} style={{
                padding: '10px 14px', textAlign: 'left',
                fontSize: 10, fontFamily: FONT_MONO, letterSpacing: '0.1em',
                textTransform: 'uppercase', color: T.textMute, fontWeight: 500, whiteSpace: 'nowrap',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((g, i) => (
            <tr key={g.key}
              onClick={() => onViewFlow(g)}
              style={{ borderBottom: `1px solid ${T.border}`, background: i % 2 === 0 ? 'transparent' : `${T.bg}66`, cursor: 'pointer', transition: 'background 0.12s' }}
              onMouseEnter={e => e.currentTarget.style.background = T.panelHi}
              onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : `${T.bg}66`}>
              <td style={{ padding: '12px 14px', fontFamily: FONT_MONO, fontSize: 12, color: T.text, fontWeight: 500 }}>{g.sourceAgent}</td>
              <td style={{ padding: '12px 14px', fontFamily: FONT_MONO, fontSize: 11, color: T.textDim, whiteSpace: 'nowrap' }}>{fmtDate(g.lastSeenIso)}</td>
              <td style={{ padding: '12px 14px', fontFamily: FONT_MONO, fontSize: 12, color: T.text }}>{g.relationshipCount}</td>
              <td style={{ padding: '12px 14px' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {g.targetTypes.map(t => <TypeBadge key={t} type={t} />)}
                </div>
              </td>
              <td style={{ padding: '12px 14px', fontFamily: FONT_MONO, fontSize: 12, color: T.text }}>{g.requests.toLocaleString()}</td>
              <td style={{ padding: '12px 14px', fontFamily: FONT_MONO, fontSize: 11, color: T.textDim }}>{g.strengthSummary}</td>
              <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                <button
                  onClick={e => { e.stopPropagation(); onViewFlow(g) }}
                  style={{ background: `${T.accent}18`, border: `1px solid ${T.accent}44`, color: T.accent, padding: '5px 12px', borderRadius: 4, fontSize: 10, fontFamily: FONT_MONO, cursor: 'pointer', letterSpacing: '0.06em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
                  View Flow →
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Graphical runtime-flow modal ────────────────────────────────────────────────

// Chain rel types render as the main left-to-right path; everything else branches.
const CHAIN_TYPES = ['routes_via', 'uses_provider', 'uses_model']

const relFor = (r) =>
  REL_META[r.relationship_type] || { color: T.textDim, label: (r.relationship_type || 'touches_system').replace(/_/g, ' ') }

/** Circular icon node used by the Path and Graph views. */
function PathNode({ type, label, sub, size = 48, strength }) {
  const m = TYPE_META[type] || TYPE_META.unknown
  const NodeIcon = m.Icon || HelpCircle
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, width: 148, flexShrink: 0 }}>
      <div style={{
        width: size, height: size, borderRadius: '50%', background: `${m.color}14`,
        border: `1.5px solid ${m.color}55`, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <NodeIcon size={Math.round(size * 0.42)} color={m.color} strokeWidth={1.8} />
      </div>
      <div style={{ textAlign: 'center', minWidth: 0, maxWidth: 148 }}>
        <div style={{ fontSize: 8.5, fontFamily: FONT_MONO, letterSpacing: '0.1em', textTransform: 'uppercase', color: m.color }}>{m.label}</div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
          <span title={label} style={{ fontSize: 12.5, color: T.text, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
          {strength && <span title={strength.why} style={{ width: 7, height: 7, borderRadius: '50%', background: strength.color, flexShrink: 0 }} />}
        </div>
        {sub && <div title={sub} style={{ fontSize: 9.5, fontFamily: FONT_MONO, color: T.textMute, marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sub}</div>}
      </div>
    </div>
  )
}

/** Labeled edge between two PathNodes: rel pill over a strength-colored line. */
function PathEdge({ r }) {
  const rel = relFor(r)
  const ev = relationshipEvidenceLabel(r)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flex: '1 0 96px', minWidth: 96, padding: '2px 4px 0' }}>
      <span style={{ padding: '1px 8px', borderRadius: 999, fontSize: 9.5, fontFamily: FONT_MONO, background: `${rel.color}14`, color: rel.color, border: `1px solid ${rel.color}33`, whiteSpace: 'nowrap' }}>{rel.label}</span>
      <div style={{ position: 'relative', width: '100%', height: 2, background: `${ev.color}66`, borderRadius: 1 }}>
        <span style={{ position: 'absolute', right: -1, top: -3, width: 0, height: 0, borderTop: '4px solid transparent', borderBottom: '4px solid transparent', borderLeft: `6px solid ${ev.color}99` }} />
      </div>
      <span title={ev.why} style={{ fontSize: 9, fontFamily: FONT_MONO, color: T.textMute, whiteSpace: 'nowrap' }}>
        {(r.request_count || 0).toLocaleString()} req · {ev.label.toLowerCase()}
      </span>
    </div>
  )
}

/** View A — Wiz-style horizontal path: agent → gateway → provider → model, extras branch below. */
function FlowPathView({ group, ordered }) {
  const chain = ordered.filter(r => CHAIN_TYPES.includes(r.relationship_type))
  const branches = ordered.filter(r => !CHAIN_TYPES.includes(r.relationship_type))
  return (
    <div>
      <div style={{ overflowX: 'auto', padding: '14px 4px 8px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'safe center', margin: '0 auto', width: 'fit-content', minWidth: '100%' }}>
          <PathNode type="agent" label={group.sourceAgent} />
          {chain.map((r, i) => (
            <Fragment key={r.id ?? `c${i}`}>
              <PathEdge r={r} />
              <PathNode type={r.target_type} label={r.target_name} sub={r.target_identifier || undefined} strength={relationshipEvidenceLabel(r)} />
            </Fragment>
          ))}
          {chain.length === 0 && branches.slice(0, 3).map((r, i) => (
            <Fragment key={r.id ?? `f${i}`}>
              <PathEdge r={r} />
              <PathNode type={r.target_type} label={r.target_name} sub={r.target_identifier || undefined} strength={relationshipEvidenceLabel(r)} />
            </Fragment>
          ))}
        </div>
      </div>
      {chain.length > 0 && branches.length > 0 && (
        <div style={{ marginTop: 16, borderTop: `1px dashed ${T.border}`, paddingTop: 14 }}>
          <div style={{ fontSize: 9.5, fontFamily: FONT_MONO, letterSpacing: '0.1em', textTransform: 'uppercase', color: T.textMute, marginBottom: 10 }}>
            Also touches
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            {branches.map((r, i) => {
              const m = TYPE_META[r.target_type] || TYPE_META.unknown
              const BranchIcon = m.Icon || HelpCircle
              const rel = relFor(r)
              const ev = relationshipEvidenceLabel(r)
              return (
                <div key={r.id ?? `b${i}`} style={{ display: 'flex', alignItems: 'center', gap: 10, border: `1px solid ${T.border}`, borderRadius: 10, padding: '8px 12px', background: T.panel }}>
                  <span style={{ width: 30, height: 30, borderRadius: '50%', background: `${m.color}14`, border: `1.5px solid ${m.color}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <BranchIcon size={13} color={m.color} strokeWidth={1.8} />
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ padding: '1px 7px', borderRadius: 999, fontSize: 9, fontFamily: FONT_MONO, background: `${rel.color}14`, color: rel.color, border: `1px solid ${rel.color}33`, whiteSpace: 'nowrap' }}>{rel.label}</span>
                      <span style={{ fontSize: 12, color: T.text, fontWeight: 600 }}>{r.target_name}</span>
                      <span title={ev.why} style={{ width: 6, height: 6, borderRadius: '50%', background: ev.color, flexShrink: 0 }} />
                    </div>
                    <div style={{ fontSize: 9, fontFamily: FONT_MONO, color: T.textMute, marginTop: 2 }}>
                      {m.label} · {(r.request_count || 0).toLocaleString()} req
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/** View B — CrowdStrike-style fan-out: agent root left, bezier elbows to each target. */
function FlowGraphView({ group, ordered }) {
  const rowH = 74
  const gapW = 190
  const H = Math.max(ordered.length * rowH, rowH)
  const rootY = H / 2
  const agentMeta = TYPE_META.agent
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', overflowX: 'auto', padding: '6px 2px' }}>
      {/* Root agent */}
      <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, border: `1px solid ${agentMeta.color}40`, background: `${agentMeta.color}0A`, borderRadius: 14, padding: '14px 18px', maxWidth: 240 }}>
          <span style={{ width: 44, height: 44, borderRadius: '50%', background: `${agentMeta.color}14`, border: `1.5px solid ${agentMeta.color}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Bot size={19} color={agentMeta.color} strokeWidth={1.8} />
          </span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 8.5, fontFamily: FONT_MONO, letterSpacing: '0.1em', textTransform: 'uppercase', color: agentMeta.color }}>Agent</div>
            <div title={group.sourceAgent} style={{ fontSize: 13, color: T.text, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{group.sourceAgent}</div>
            <div style={{ fontSize: 9, fontFamily: FONT_MONO, color: T.textMute, marginTop: 1 }}>{ordered.length} runtime link{ordered.length !== 1 ? 's' : ''}</div>
          </div>
        </div>
      </div>

      {/* Elbow connectors */}
      <div style={{ position: 'relative', width: gapW, flexShrink: 0 }}>
        <svg width={gapW} height={H} style={{ display: 'block' }}>
          {ordered.map((r, i) => {
            const y = i * rowH + rowH / 2
            const ev = relationshipEvidenceLabel(r)
            return (
              <path key={r.id ?? i}
                d={`M 0 ${rootY} C ${gapW * 0.45} ${rootY}, ${gapW * 0.55} ${y}, ${gapW} ${y}`}
                fill="none" stroke={ev.color} strokeOpacity="0.55" strokeWidth="2" strokeLinecap="round" />
            )
          })}
          <circle cx="2" cy={rootY} r="3.5" fill={agentMeta.color} />
        </svg>
        {ordered.map((r, i) => {
          const rel = relFor(r)
          const y = (rootY + (i * rowH + rowH / 2)) / 2
          return (
            <span key={r.id ?? i} style={{
              position: 'absolute', left: '50%', top: y, transform: 'translate(-50%, -50%)',
              padding: '1px 8px', borderRadius: 999, fontSize: 9, fontFamily: FONT_MONO,
              background: '#FFFFFF', color: rel.color, border: `1px solid ${rel.color}40`, whiteSpace: 'nowrap',
            }}>{rel.label}</span>
          )
        })}
      </div>

      {/* Targets */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 220 }}>
        {ordered.map((r, i) => {
          const m = TYPE_META[r.target_type] || TYPE_META.unknown
          const TargetIcon = m.Icon || HelpCircle
          const ev = relationshipEvidenceLabel(r)
          return (
            <div key={r.id ?? i} style={{ height: rowH, display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ width: 40, height: 40, borderRadius: '50%', background: `${m.color}14`, border: `1.5px solid ${m.color}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <TargetIcon size={17} color={m.color} strokeWidth={1.8} />
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 8.5, fontFamily: FONT_MONO, letterSpacing: '0.1em', textTransform: 'uppercase', color: m.color }}>{m.label}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span title={r.target_name} style={{ fontSize: 13, color: T.text, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.target_name}</span>
                  <span title={ev.why} style={{ width: 7, height: 7, borderRadius: '50%', background: ev.color, flexShrink: 0 }} />
                </div>
                <div style={{ fontSize: 9.5, fontFamily: FONT_MONO, color: T.textMute, marginTop: 1 }}>
                  {(r.request_count || 0).toLocaleString()} req · {fmtDate(r.last_seen_at)}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function FlowModal({ group, onClose }) {
  const [flowView, setFlowView] = useState('path')
  const ordered = [...group.rows].sort((a, b) => relOrder(a.relationship_type) - relOrder(b.relationship_type))
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 16, boxShadow: '0 20px 50px rgba(15,23,42,0.18)', width: '100%', maxWidth: 920, maxHeight: '86vh', display: 'flex', flexDirection: 'column', fontFamily: FONT_SANS }}>

        {/* Header */}
        <div style={{ padding: '20px 24px 14px', borderBottom: `1px solid ${T.border}` }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: T.text }}>Runtime Flow: {group.sourceAgent}</div>
              <div style={{ fontSize: 11, color: T.textMute, fontFamily: FONT_MONO, marginTop: 4 }}>
                Observed {fmtDate(group.lastSeenIso)} · {group.requests.toLocaleString()} requests · {group.strengthSummary} evidence
              </div>
            </div>
            <div style={{ display: 'flex', gap: 0, background: T.panelHi, border: `1px solid ${T.border}`, borderRadius: 8, padding: 3 }}>
              {[
                { id: 'path',  label: 'Path' },
                { id: 'graph', label: 'Graph' },
                { id: 'table', label: 'Table' },
              ].map(t => (
                <button key={t.id} onClick={() => setFlowView(t.id)}
                  style={{
                    background: flowView === t.id ? T.panel : 'transparent',
                    border: flowView === t.id ? `1px solid ${T.border}` : '1px solid transparent',
                    color: flowView === t.id ? T.text : T.textDim,
                    boxShadow: flowView === t.id ? '0 1px 2px rgba(15,23,42,0.06)' : 'none',
                    padding: '5px 14px', borderRadius: 6, fontSize: 11, fontFamily: FONT_MONO, cursor: 'pointer',
                  }}>
                  {t.label}
                </button>
              ))}
            </div>
            <button onClick={onClose} style={{ background: 'transparent', border: `1px solid ${T.border}`, color: T.textDim, padding: '6px 14px', borderRadius: 8, fontSize: 12, fontFamily: FONT_MONO, cursor: 'pointer' }}>✕ Close</button>
          </div>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '24px' }}>
          {flowView === 'path' && <FlowPathView group={group} ordered={ordered} />}
          {flowView === 'graph' && <FlowGraphView group={group} ordered={ordered} />}
          {flowView === 'table' && (
          <div style={{ border: `1px solid ${T.border}`, borderRadius: 6, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${T.border}`, background: T.panelHi }}>
                  {['Relationship', 'Target', 'Evidence', 'Strength', 'Requests', 'Last Seen'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: 10, fontFamily: FONT_MONO, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.textMute, fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ordered.map((r, i) => (
                  <tr key={r.id ?? i} style={{ borderBottom: `1px solid ${T.border}` }}>
                    <td style={{ padding: '9px 12px' }}><RelBadge type={r.relationship_type} /></td>
                    <td style={{ padding: '9px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <TypeBadge type={r.target_type} />
                        <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: T.text }}>{r.target_name}</span>
                      </div>
                    </td>
                    <td style={{ padding: '9px 12px', fontFamily: FONT_MONO, fontSize: 10, color: T.textDim }}>{r.evidence_source}</td>
                    <td style={{ padding: '9px 12px' }}><StrengthBadge rel={r} /></td>
                    <td style={{ padding: '9px 12px', fontFamily: FONT_MONO, fontSize: 12, color: T.text }}>{(r.request_count || 0).toLocaleString()}</td>
                    <td style={{ padding: '9px 12px', fontFamily: FONT_MONO, fontSize: 11, color: T.textDim }}>{fmtDate(r.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
        </div>
      </div>
    </div>
  )
}
