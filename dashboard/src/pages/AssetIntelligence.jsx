import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  fetchIntelligenceAssets, fetchIntelligenceCapabilities, fetchIntelligenceFindings,
  runIntelligence, dismissFinding, resolveFinding,
} from "../api.js";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { Card, Stat, Pill, SortableTh, SearchBox, useSortable, useSearch } from "../components/ui.jsx";
import { useUser } from "../auth.jsx";

const SEV_COLOR = { critical: T.crit, high: T.crit, medium: T.warn, low: T.info, info: T.textDim };
const CATEGORY_COLOR = {
  security: T.crit, performance: T.purple, operations: T.info,
  dependency: T.teal, inventory: T.accent, governance: T.warn,
};
const CAP_COLOR = {
  provider: T.info, model: T.purple, mcp: T.warn, database: T.crit, filesystem: T.warn,
  shell: T.crit, messaging: T.teal, source_control: T.teal, crm: T.warn,
  retrieval: T.accent, memory: T.accent, external_api: T.info, runtime: T.textDim, unknown: T.textDim,
};

const fmtWhen = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

const TabButton = ({ active, onClick, children, count }) => (
  <button onClick={onClick}
    style={{ background: active ? T.panelHi : "transparent", color: active ? T.text : T.textDim,
      border: `1px solid ${active ? T.borderHi : T.border}`, borderBottom: active ? `2px solid ${T.accent}` : `1px solid ${T.border}`,
      padding: "8px 18px", borderRadius: "5px 5px 0 0", fontSize: 12, fontFamily: FONT_UI, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8 }}>
    {children}
    {count != null && <span style={{ fontFamily: FONT_MONO, fontSize: 10, color: active ? T.accent : T.textMute }}>{count}</span>}
  </button>
);

const FilterSelect = ({ value, onChange, options, allLabel }) => (
  <select value={value} onChange={(e) => onChange(e.target.value)}
    style={{ background: T.panelHi, color: T.text, border: `1px solid ${T.border}`, padding: "6px 8px", borderRadius: 4, fontSize: 12, fontFamily: FONT_MONO, cursor: "pointer" }}>
    <option value="all">{allLabel}</option>
    {options.map((o) => <option key={o} value={o}>{o}</option>)}
  </select>
);

const EmptyState = ({ title, hint }) => (
  <div style={{ padding: "40px 20px", textAlign: "center" }}>
    <div style={{ color: T.textDim, fontSize: 14, marginBottom: 6 }}>{title}</div>
    <div style={{ color: T.textMute, fontSize: 12, fontFamily: FONT_MONO }}>{hint}</div>
  </div>
);

// ── Discovered assets tab (Runtime Discovery evidence) ────────────────────────

function AssetsTab({ assets, loading }) {
  const { query, setQuery, filtered } = useSearch(assets, (a) =>
    `${a.service_name} ${a.agent_name || ""} ${a.environment || ""} ${(a.models || []).join(" ")} ${(a.providers || []).join(" ")}`);
  const { sortKey, sortDir, toggle, sort } = useSortable("last_seen");
  const rows = sort(filtered, (a, key) => a[key]);
  const [expanded, setExpanded] = useState(null);

  if (loading) return <div style={{ padding: "40px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 13 }}>Loading…</div>;
  if (assets.length === 0) return (
    <EmptyState title="No AI systems discovered from telemetry yet"
      hint="Point an OpenTelemetry exporter at POST /otel/v1/traces — discovered services appear here with their models, providers, and tools." />
  );

  return (
    <div>
      <SearchBox query={query} onChange={setQuery} placeholder="Search assets…" count={filtered.length} total={assets.length} />
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: FONT_UI }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${T.border}` }}>
              <SortableTh label="Service"     sortKey="service_name" active={sortKey === "service_name"} dir={sortDir} onToggle={toggle} />
              <SortableTh label="Environment" sortKey="environment"  active={sortKey === "environment"}  dir={sortDir} onToggle={toggle} />
              <SortableTh label="Models"      sortKey="models"       active={false} dir={sortDir} onToggle={() => {}} />
              <SortableTh label="Tools"       sortKey="tools"        active={false} dir={sortDir} onToggle={() => {}} />
              <SortableTh label="Spans"       sortKey="span_count"   active={sortKey === "span_count"}   dir={sortDir} onToggle={toggle} />
              <SortableTh label="Last seen"   sortKey="last_seen"    active={sortKey === "last_seen"}    dir={sortDir} onToggle={toggle} />
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <React.Fragment key={a.id}>
                <tr onClick={() => setExpanded(expanded === a.id ? null : a.id)}
                  style={{ borderBottom: `1px solid ${T.border}`, cursor: "pointer" }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = T.panelHi; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                  <td style={{ padding: "10px 8px", fontSize: 13, color: T.text }}>
                    {a.service_name}
                    {a.agent_name && a.agent_name !== a.service_name && (
                      <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11, marginLeft: 8 }}>({a.agent_name})</span>
                    )}
                  </td>
                  <td style={{ padding: "10px 8px" }}>
                    {a.environment
                      ? <Pill color={["production", "prod"].includes(a.environment.toLowerCase()) ? T.warn : T.info}>{a.environment}</Pill>
                      : <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>—</span>}
                  </td>
                  <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>
                    {(a.models || []).slice(0, 2).join(", ") || "—"}{(a.models || []).length > 2 ? ` +${a.models.length - 2}` : ""}
                  </td>
                  <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>{(a.tools || []).length}</td>
                  <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>{a.span_count}</td>
                  <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO, whiteSpace: "nowrap" }}>{fmtWhen(a.last_seen)}</td>
                </tr>
                {expanded === a.id && (
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    <td colSpan={6} style={{ padding: "14px 18px", background: T.panelHi }}>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, fontSize: 12 }}>
                        {[["Providers", a.providers], ["Models", a.models], ["Tools", a.tools], ["Dependencies", a.dependencies]].map(([label, items]) => (
                          <div key={label}>
                            <div style={{ fontFamily: FONT_MONO, fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase", color: T.textMute, marginBottom: 6 }}>{label}</div>
                            {(items || []).length === 0
                              ? <span style={{ color: T.textMute, fontFamily: FONT_MONO }}>—</span>
                              : <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                  {items.map((m) => <Pill key={m} color={T.info}>{m}</Pill>)}
                                </div>}
                          </div>
                        ))}
                      </div>
                      <div style={{ marginTop: 12, fontFamily: FONT_MONO, fontSize: 11, color: T.textMute }}>
                        first seen {fmtWhen(a.first_seen)} · {a.trace_count} traces · {a.span_count} spans
                        {a.ai_asset_id && <span> · inventory asset #{a.ai_asset_id}</span>}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Capabilities tab ──────────────────────────────────────────────────────────

function CapabilitiesTab({ capabilities, loading }) {
  const [typeFilter, setTypeFilter] = useState("all");
  const types = useMemo(() => [...new Set(capabilities.map((c) => c.capability_type))].sort(), [capabilities]);
  const byType = typeFilter === "all" ? capabilities : capabilities.filter((c) => c.capability_type === typeFilter);

  const { query, setQuery, filtered } = useSearch(byType, (c) => `${c.capability_name} ${c.capability_type} ${c.source}`);
  const { sortKey, sortDir, toggle, sort } = useSortable("last_seen");
  const rows = sort(filtered, (c, key) => c[key]);

  if (loading) return <div style={{ padding: "40px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 13 }}>Loading…</div>;
  if (capabilities.length === 0) return (
    <EmptyState title="No capabilities derived yet"
      hint="Run intelligence after ingesting OTel traces — capability rows describe what each AI system can do." />
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start", flexWrap: "wrap" }}>
        <SearchBox query={query} onChange={setQuery} placeholder="Search capabilities…" count={filtered.length} total={byType.length} />
        <FilterSelect value={typeFilter} onChange={setTypeFilter} options={types} allLabel="All types" />
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: FONT_UI }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${T.border}` }}>
              <SortableTh label="Capability" sortKey="capability_name" active={sortKey === "capability_name"} dir={sortDir} onToggle={toggle} />
              <SortableTh label="Type"       sortKey="capability_type" active={sortKey === "capability_type"} dir={sortDir} onToggle={toggle} />
              <SortableTh label="Source"     sortKey="source"          active={sortKey === "source"}          dir={sortDir} onToggle={toggle} />
              <SortableTh label="First seen" sortKey="first_seen"      active={sortKey === "first_seen"}      dir={sortDir} onToggle={toggle} />
              <SortableTh label="Last seen"  sortKey="last_seen"       active={sortKey === "last_seen"}       dir={sortDir} onToggle={toggle} />
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} style={{ borderBottom: `1px solid ${T.border}` }}>
                <td style={{ padding: "10px 8px", fontSize: 13, color: T.text, fontFamily: FONT_MONO }}>{c.capability_name}</td>
                <td style={{ padding: "10px 8px" }}><Pill color={CAP_COLOR[c.capability_type] || T.textDim}>{c.capability_type}</Pill></td>
                <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>{c.source}</td>
                <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO, whiteSpace: "nowrap" }}>{fmtWhen(c.first_seen)}</td>
                <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO, whiteSpace: "nowrap" }}>{fmtWhen(c.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Findings tab ──────────────────────────────────────────────────────────────

function FindingsTab({ findings, loading, canAct, onAction }) {
  const [catFilter, setCatFilter] = useState("all");
  const [sevFilter, setSevFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("open");
  const [expanded, setExpanded] = useState(null);
  const [actionErr, setActionErr] = useState(null);

  const cats = useMemo(() => [...new Set(findings.map((f) => f.category))].sort(), [findings]);
  const sevs = ["critical", "high", "medium", "low", "info"].filter((s) => findings.some((f) => f.severity === s));

  const visible = findings.filter((f) =>
    (catFilter === "all" || f.category === catFilter) &&
    (sevFilter === "all" || f.severity === sevFilter) &&
    (statusFilter === "all" || f.status === statusFilter));

  const { query, setQuery, filtered } = useSearch(visible, (f) => `${f.title} ${f.finding_type} ${f.category} ${f.severity}`);
  const SEV_RANK = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };
  const { sortKey, sortDir, toggle, sort } = useSortable("severity");
  const rows = sort(filtered, (f, key) => key === "severity" ? SEV_RANK[f.severity] ?? 0 : f[key]);

  const act = (f, action) => {
    setActionErr(null);
    (action === "dismiss" ? dismissFinding(f.id) : resolveFinding(f.id))
      .then(() => onAction())
      .catch((e) => setActionErr(e.message));
  };

  if (loading) return <div style={{ padding: "40px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 13 }}>Loading…</div>;
  if (findings.length === 0) return (
    <EmptyState title="No findings"
      hint="Run intelligence after ingesting OTel traces — findings are normalized signals across security, performance, operations, dependency, and inventory." />
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start", flexWrap: "wrap" }}>
        <SearchBox query={query} onChange={setQuery} placeholder="Search findings…" count={filtered.length} total={visible.length} />
        <FilterSelect value={catFilter}    onChange={setCatFilter}    options={cats} allLabel="All categories" />
        <FilterSelect value={sevFilter}    onChange={setSevFilter}    options={sevs} allLabel="All severities" />
        <FilterSelect value={statusFilter} onChange={setStatusFilter} options={["open", "dismissed", "resolved"]} allLabel="All statuses" />
      </div>

      {actionErr && (
        <div style={{ padding: "10px 14px", background: `${T.crit}0D`, border: `1px solid ${T.crit}33`, borderRadius: 4, color: T.crit, fontFamily: FONT_MONO, fontSize: 12, marginBottom: 10 }}>
          {actionErr}
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: FONT_UI }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${T.border}` }}>
              <SortableTh label="Finding"   sortKey="title"     active={sortKey === "title"}     dir={sortDir} onToggle={toggle} />
              <SortableTh label="Category"  sortKey="category"  active={sortKey === "category"}  dir={sortDir} onToggle={toggle} />
              <SortableTh label="Severity"  sortKey="severity"  active={sortKey === "severity"}  dir={sortDir} onToggle={toggle} />
              <SortableTh label="Status"    sortKey="status"    active={sortKey === "status"}    dir={sortDir} onToggle={toggle} />
              <SortableTh label="Last seen" sortKey="last_seen" active={sortKey === "last_seen"} dir={sortDir} onToggle={toggle} />
              {canAct && <th style={{ padding: "10px 8px" }} />}
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <React.Fragment key={f.id}>
                <tr onClick={() => setExpanded(expanded === f.id ? null : f.id)}
                  style={{ borderBottom: `1px solid ${T.border}`, cursor: "pointer", opacity: f.status === "open" ? 1 : 0.55 }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = T.panelHi; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                  <td style={{ padding: "10px 8px", fontSize: 13, color: T.text }}>{f.title}</td>
                  <td style={{ padding: "10px 8px" }}><Pill color={CATEGORY_COLOR[f.category] || T.textDim}>{f.category}</Pill></td>
                  <td style={{ padding: "10px 8px" }}><Pill color={SEV_COLOR[f.severity] || T.textDim}>{f.severity}</Pill></td>
                  <td style={{ padding: "10px 8px", fontSize: 12, fontFamily: FONT_MONO, color: f.status === "open" ? T.warn : T.textMute }}>{f.status}</td>
                  <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO, whiteSpace: "nowrap" }}>{fmtWhen(f.last_seen)}</td>
                  {canAct && (
                    <td style={{ padding: "10px 8px", whiteSpace: "nowrap" }} onClick={(e) => e.stopPropagation()}>
                      {f.status === "open" && (
                        <span style={{ display: "inline-flex", gap: 6 }}>
                          <button onClick={() => act(f, "resolve")}
                            style={{ background: "transparent", color: T.accent, border: `1px solid ${T.accent}44`, padding: "3px 10px", borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer" }}>
                            Resolve
                          </button>
                          <button onClick={() => act(f, "dismiss")}
                            style={{ background: "transparent", color: T.textDim, border: `1px solid ${T.border}`, padding: "3px 10px", borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer" }}>
                            Dismiss
                          </button>
                        </span>
                      )}
                    </td>
                  )}
                </tr>
                {expanded === f.id && (
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    <td colSpan={canAct ? 6 : 5} style={{ padding: "14px 18px", background: T.panelHi }}>
                      <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6, marginBottom: 8 }}>{f.summary}</div>
                      <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: T.textMute }}>
                        {f.finding_type} · source {f.source} · first seen {fmtWhen(f.first_seen)}
                      </div>
                      {f.evidence && (
                        <pre style={{ marginTop: 10, marginBottom: 0, padding: "10px 12px", background: T.panel, border: `1px solid ${T.border}`, borderRadius: 4, fontFamily: FONT_MONO, fontSize: 11, color: T.textDim, overflowX: "auto" }}>
                          {JSON.stringify(f.evidence, null, 2)}
                        </pre>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AssetIntelligence() {
  const user = useUser();
  const canAct = ["admin", "analyst"].includes(user?.role) || user?.is_platform_admin;

  const [tab, setTab] = useState("assets");
  const [assets, setAssets]             = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [findings, setFindings]         = useState([]);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [running, setRunning]           = useState(false);
  const [runResult, setRunResult]       = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetchIntelligenceAssets(),
      fetchIntelligenceCapabilities(),
      fetchIntelligenceFindings(),
    ])
      .then(([a, c, f]) => { setAssets(a); setCapabilities(c); setFindings(f); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRun = () => {
    setRunning(true);
    setRunResult(null);
    setError(null);
    runIntelligence()
      .then((res) => {
        setRunResult(`${res.capabilities_created + res.capabilities_updated} capabilities · ${res.findings_created + res.findings_updated} findings`);
        load();
      })
      .catch((e) => setError(e.message))
      .finally(() => setRunning(false));
  };

  const openFindings = findings.filter((f) => f.status === "open");
  const highSev = openFindings.filter((f) => ["critical", "high"].includes(f.severity)).length;

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginBottom: 14 }}>
        <Stat label="Discovered assets" value={assets.length} />
        <Stat label="Capabilities"      value={capabilities.length} />
        <Stat label="Open findings"     value={openFindings.length} />
        <Stat label="High severity"     value={highSev} accent={highSev > 0 ? T.crit : T.text} />
      </div>

      <Card
        title="Asset Intelligence"
        subtitle="What each AI system can do, and what its observed behavior means — derived from runtime telemetry"
        right={
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {runResult && <span style={{ fontFamily: FONT_MONO, fontSize: 10, color: T.accent }}>✓ {runResult}</span>}
            {canAct && (
              <button onClick={handleRun} disabled={running}
                style={{ background: T.accent, color: T.bg, border: "none", padding: "6px 14px", borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO, fontWeight: 600, cursor: "pointer", letterSpacing: "0.08em", textTransform: "uppercase", opacity: running ? 0.5 : 1 }}>
                {running ? "Running…" : "▶ Run intelligence"}
              </button>
            )}
            <button onClick={load}
              style={{ background: "transparent", color: T.textDim, border: `1px solid ${T.border}`, padding: "5px 12px", borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              ↻ Refresh
            </button>
          </div>
        }>

        {error && (
          <div style={{ padding: "12px 14px", background: `${T.crit}0D`, border: `1px solid ${T.crit}33`, borderRadius: 4, color: T.crit, fontFamily: FONT_MONO, fontSize: 12, marginBottom: 12 }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: `1px solid ${T.border}` }}>
          <TabButton active={tab === "assets"}       onClick={() => setTab("assets")}       count={assets.length}>Discovered Assets</TabButton>
          <TabButton active={tab === "capabilities"} onClick={() => setTab("capabilities")} count={capabilities.length}>Capabilities</TabButton>
          <TabButton active={tab === "findings"}     onClick={() => setTab("findings")}     count={openFindings.length}>Findings</TabButton>
        </div>

        {tab === "assets"       && <AssetsTab assets={assets} loading={loading} />}
        {tab === "capabilities" && <CapabilitiesTab capabilities={capabilities} loading={loading} />}
        {tab === "findings"     && <FindingsTab findings={findings} loading={loading} canAct={canAct} onAction={load} />}
      </Card>
    </div>
  );
}
