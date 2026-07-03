import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  fetchIntelligenceAssetSummary, fetchIntelligenceCapabilities, fetchIntelligenceFindings,
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
const STATUS_META = {
  active:           { label: "Active",           color: T.accent },
  runtime_observed: { label: "Runtime observed", color: T.info },
  has_findings:     { label: "Has findings",     color: T.warn },
  error_observed:   { label: "Error observed",   color: T.crit },
};

const fmtWhen = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

// Shorten URLs for display: https://api.foo.example/v2/lookup → api.foo.example
const displayUrl = (name) => {
  if (typeof name !== "string" || !/^https?:\/\//i.test(name)) return name;
  try { return new URL(name).hostname; } catch { return name.replace(/^https?:\/\//i, "").split("/")[0]; }
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
    {options.map((o) => (typeof o === "string"
      ? <option key={o} value={o}>{o}</option>
      : <option key={o.value} value={o.value}>{o.label}</option>))}
  </select>
);

const EmptyState = ({ title, hint }) => (
  <div style={{ padding: "40px 20px", textAlign: "center" }}>
    <div style={{ color: T.textDim, fontSize: 14, marginBottom: 6 }}>{title}</div>
    {hint && <div style={{ color: T.textMute, fontSize: 12, fontFamily: FONT_MONO }}>{hint}</div>}
  </div>
);

const SectionLabel = ({ children }) => (
  <div style={{ fontFamily: FONT_MONO, fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase", color: T.textMute, marginBottom: 6 }}>{children}</div>
);

const ChipGroup = ({ label, items, color, max = 6, shorten = false }) => (
  <div style={{ minWidth: 160 }}>
    <SectionLabel>{label}</SectionLabel>
    {(items || []).length === 0
      ? <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>—</span>
      : <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {items.slice(0, max).map((m) => <Pill key={m} color={color}>{shorten ? displayUrl(m) : m}</Pill>)}
          {items.length > max && <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>+{items.length - max}</span>}
        </div>}
  </div>
);

// ── AI Systems tab ────────────────────────────────────────────────────────────

function FindingRow({ f, canAct, onAction }) {
  const [showEvidence, setShowEvidence] = useState(false);
  return (
    <div style={{ borderBottom: `1px solid ${T.border}`, padding: "8px 0", opacity: f.status === "open" ? 1 : 0.55 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Pill color={SEV_COLOR[f.severity] || T.textDim}>{f.severity}</Pill>
        <Pill color={CATEGORY_COLOR[f.category] || T.textDim}>{f.category}</Pill>
        <span style={{ fontSize: 13, color: T.text }}>{f.title}</span>
        <span style={{ fontFamily: FONT_MONO, fontSize: 11, color: f.status === "open" ? T.warn : T.textMute, marginLeft: "auto" }}>{f.status}</span>
        {canAct && f.status === "open" && (
          <span style={{ display: "inline-flex", gap: 6 }}>
            <button onClick={() => onAction(f, "resolve")}
              style={{ background: "transparent", color: T.accent, border: `1px solid ${T.accent}44`, padding: "2px 8px", borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer" }}>
              Resolve
            </button>
            <button onClick={() => onAction(f, "dismiss")}
              style={{ background: "transparent", color: T.textDim, border: `1px solid ${T.border}`, padding: "2px 8px", borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer" }}>
              Dismiss
            </button>
          </span>
        )}
      </div>
      <div style={{ fontSize: 12, color: T.textDim, marginTop: 4, lineHeight: 1.5 }}>{f.summary}</div>
      {f.evidence && (
        <div style={{ marginTop: 4 }}>
          <button onClick={() => setShowEvidence((v) => !v)}
            style={{ background: "none", border: "none", color: T.textMute, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer", padding: 0 }}>
            {showEvidence ? "▾ Hide raw evidence" : "▸ Raw evidence"}
          </button>
          {showEvidence && (
            <pre style={{ margin: "6px 0 0", padding: "8px 10px", background: T.panel, border: `1px solid ${T.border}`, borderRadius: 4, fontFamily: FONT_MONO, fontSize: 11, color: T.textDim, overflowX: "auto" }}>
              {JSON.stringify(f.evidence, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function AssetCard({ asset, expanded, onToggle, canAct, onFindingAction }) {
  const a = asset;
  const findingBits = [];
  if (a.open_findings_count > 0) findingBits.push(`${a.open_findings_count} open`);
  if (a.high_findings_count > 0) findingBits.push(`${a.high_findings_count} high`);
  Object.entries(a.finding_categories || {}).forEach(([cat, n]) => findingBits.push(`${n} ${cat}`));

  return (
    <div style={{ background: T.panelHi, border: `1px solid ${expanded ? T.borderHi : T.border}`, borderRadius: 6, overflow: "hidden" }}>
      <div onClick={onToggle} style={{ padding: "14px 16px", cursor: "pointer" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
          <span style={{ fontSize: 15, color: T.text, fontWeight: 500, fontFamily: FONT_MONO }}>{a.asset_name}</span>
          {a.environment && (
            <Pill color={["production", "prod"].includes(a.environment.toLowerCase()) ? T.warn : T.info}>{a.environment}</Pill>
          )}
          <span style={{ display: "inline-flex", gap: 6, marginLeft: "auto", flexWrap: "wrap" }}>
            {(a.status || []).map((s) => {
              const meta = STATUS_META[s];
              return meta ? <Pill key={s} color={meta.color}>{meta.label}</Pill> : null;
            })}
          </span>
        </div>

        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginBottom: 10 }}>
          <ChipGroup label="Models"       items={a.models}       color={CAP_COLOR.model} />
          <ChipGroup label="Providers"    items={a.providers}    color={CAP_COLOR.provider} />
          <ChipGroup label="Tools"        items={a.tools}        color={T.teal} />
          <ChipGroup label="Dependencies" items={a.dependencies} color={T.info} shorten />
        </div>

        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", fontFamily: FONT_MONO, fontSize: 11, color: T.textDim }}>
          <span>
            <span style={{ color: T.textMute }}>findings&nbsp;</span>
            {findingBits.length ? findingBits.join(" · ") : "none"}
          </span>
          <span>
            <span style={{ color: T.textMute }}>runtime&nbsp;</span>
            {a.trace_count} trace{a.trace_count === 1 ? "" : "s"} · {a.span_count} spans · last seen {fmtWhen(a.last_seen)}
          </span>
          <span style={{ marginLeft: "auto", color: T.textMute }}>{expanded ? "▲ collapse" : "▼ details"}</span>
        </div>
      </div>

      {expanded && (
        <div style={{ borderTop: `1px solid ${T.border}`, background: T.panel, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 18 }}>
          <div>
            <SectionLabel>Runtime Evidence</SectionLabel>
            <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: T.textDim }}>
              service <span style={{ color: T.text }}>{a.service_name}</span>
              {a.environment && <> · environment <span style={{ color: T.text }}>{a.environment}</span></>}
              {" "}· {a.trace_count} trace{a.trace_count === 1 ? "" : "s"} · {a.span_count} spans · last seen {fmtWhen(a.last_seen)}
              {a.ai_asset_id && <> · inventory asset #{a.ai_asset_id}</>}
            </div>
          </div>

          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <ChipGroup label="Models & Providers" items={[...(a.models || []), ...(a.providers || [])]} color={CAP_COLOR.model} max={12} />
            <ChipGroup label="Tools"        items={a.tools}        color={T.teal} max={12} />
            <ChipGroup label="Dependencies" items={a.dependencies} color={T.info} max={12} shorten />
          </div>

          <div>
            <SectionLabel>Capabilities ({a.capabilities_count})</SectionLabel>
            {a.capabilities.length === 0
              ? <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>none derived yet — run intelligence</span>
              : <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {a.capabilities.map((c) => (
                    <span key={c.id} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <Pill color={CAP_COLOR[c.capability_type] || T.textDim}>
                        {c.capability_type}: {displayUrl(c.capability_name)}
                      </Pill>
                    </span>
                  ))}
                </div>}
          </div>

          <div>
            <SectionLabel>Findings ({a.findings.length})</SectionLabel>
            {a.findings.length === 0
              ? <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>no findings</span>
              : a.findings.map((f) => (
                  <FindingRow key={f.id} f={f} canAct={canAct} onAction={onFindingAction} />
                ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AISystemsTab({ assets, capabilitiesTotal, loading, canAct, onFindingAction }) {
  const [expanded, setExpanded] = useState(null);
  const { query, setQuery, filtered } = useSearch(assets, (a) =>
    `${a.asset_name} ${a.environment || ""} ${(a.models || []).join(" ")} ${(a.providers || []).join(" ")} ${(a.tools || []).join(" ")}`);

  if (loading) return <div style={{ padding: "40px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 13 }}>Loading…</div>;
  if (assets.length === 0) return (
    <EmptyState title="No AI systems discovered yet."
      hint="Ingest OpenTelemetry traces or run the demo seed." />
  );
  if (capabilitiesTotal === 0) return (
    <EmptyState title="Assets discovered, but no capabilities have been derived yet."
      hint="Run Intelligence to derive capabilities and findings from the collected evidence." />
  );

  return (
    <div>
      <SearchBox query={query} onChange={setQuery} placeholder="Search AI systems…" count={filtered.length} total={assets.length} />
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {filtered.map((a) => (
          <AssetCard key={a.asset_key} asset={a}
            expanded={expanded === a.asset_key}
            onToggle={() => setExpanded(expanded === a.asset_key ? null : a.asset_key)}
            canAct={canAct} onFindingAction={onFindingAction} />
        ))}
      </div>
    </div>
  );
}

// ── Capabilities tab (power users) ────────────────────────────────────────────

function CapabilitiesTab({ capabilities, assetNames, loading }) {
  const [typeFilter, setTypeFilter] = useState("all");
  const [assetFilter, setAssetFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");

  const types = useMemo(() => [...new Set(capabilities.map((c) => c.capability_type))].sort(), [capabilities]);
  const sources = useMemo(() => [...new Set(capabilities.map((c) => c.source))].sort(), [capabilities]);
  const assetOptions = useMemo(() => {
    const keys = [...new Set(capabilities.map((c) => c.asset_key).filter(Boolean))];
    return keys.map((k) => ({ value: k, label: assetNames[k] || k.slice(0, 12) + "…" }))
      .sort((x, y) => x.label.localeCompare(y.label));
  }, [capabilities, assetNames]);

  const visible = capabilities.filter((c) =>
    (typeFilter === "all" || c.capability_type === typeFilter) &&
    (assetFilter === "all" || c.asset_key === assetFilter) &&
    (sourceFilter === "all" || c.source === sourceFilter));

  const { query, setQuery, filtered } = useSearch(visible, (c) =>
    `${c.capability_name} ${c.capability_type} ${c.source} ${assetNames[c.asset_key] || ""}`);
  const { sortKey, sortDir, toggle, sort } = useSortable("last_seen");
  const rows = sort(filtered, (c, key) => key === "asset" ? (assetNames[c.asset_key] || "") : c[key]);

  if (loading) return <div style={{ padding: "40px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 13 }}>Loading…</div>;
  if (capabilities.length === 0) return (
    <EmptyState title="No capabilities derived yet."
      hint="Run Intelligence after ingesting OTel traces — capability rows describe what each AI system can do." />
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start", flexWrap: "wrap" }}>
        <SearchBox query={query} onChange={setQuery} placeholder="Search capabilities…" count={filtered.length} total={visible.length} />
        <FilterSelect value={assetFilter}  onChange={setAssetFilter}  options={assetOptions} allLabel="All assets" />
        <FilterSelect value={typeFilter}   onChange={setTypeFilter}   options={types}   allLabel="All types" />
        <FilterSelect value={sourceFilter} onChange={setSourceFilter} options={sources} allLabel="All sources" />
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: FONT_UI }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${T.border}` }}>
              <SortableTh label="Asset"      sortKey="asset"           active={sortKey === "asset"}           dir={sortDir} onToggle={toggle} />
              <SortableTh label="Capability" sortKey="capability_name" active={sortKey === "capability_name"} dir={sortDir} onToggle={toggle} />
              <SortableTh label="Type"       sortKey="capability_type" active={sortKey === "capability_type"} dir={sortDir} onToggle={toggle} />
              <SortableTh label="Source"     sortKey="source"          active={sortKey === "source"}          dir={sortDir} onToggle={toggle} />
              <SortableTh label="Last seen"  sortKey="last_seen"       active={sortKey === "last_seen"}       dir={sortDir} onToggle={toggle} />
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} style={{ borderBottom: `1px solid ${T.border}` }}>
                <td style={{ padding: "10px 8px", fontSize: 12, color: T.text, fontFamily: FONT_MONO }}>{assetNames[c.asset_key] || "—"}</td>
                <td style={{ padding: "10px 8px", fontSize: 13, color: T.text, fontFamily: FONT_MONO }}>{displayUrl(c.capability_name)}</td>
                <td style={{ padding: "10px 8px" }}><Pill color={CAP_COLOR[c.capability_type] || T.textDim}>{c.capability_type}</Pill></td>
                <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>{c.source}</td>
                <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO, whiteSpace: "nowrap" }}>{fmtWhen(c.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Findings tab (power users) ────────────────────────────────────────────────

function FindingsTab({ findings, assetNames, capabilitiesTotal, loading, canAct, onAction }) {
  const [catFilter, setCatFilter] = useState("all");
  const [sevFilter, setSevFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("open");
  const [assetFilter, setAssetFilter] = useState("all");
  const [expanded, setExpanded] = useState(null);
  const [actionErr, setActionErr] = useState(null);

  const cats = useMemo(() => [...new Set(findings.map((f) => f.category))].sort(), [findings]);
  const sevs = ["critical", "high", "medium", "low", "info"].filter((s) => findings.some((f) => f.severity === s));
  const assetOptions = useMemo(() => {
    const keys = [...new Set(findings.map((f) => f.asset_key).filter(Boolean))];
    return keys.map((k) => ({ value: k, label: assetNames[k] || k.slice(0, 12) + "…" }))
      .sort((x, y) => x.label.localeCompare(y.label));
  }, [findings, assetNames]);

  const visible = findings.filter((f) =>
    (catFilter === "all" || f.category === catFilter) &&
    (sevFilter === "all" || f.severity === sevFilter) &&
    (statusFilter === "all" || f.status === statusFilter) &&
    (assetFilter === "all" || f.asset_key === assetFilter));

  const { query, setQuery, filtered } = useSearch(visible, (f) =>
    `${f.title} ${f.finding_type} ${f.category} ${f.severity} ${assetNames[f.asset_key] || ""}`);
  const SEV_RANK = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };
  const { sortKey, sortDir, toggle, sort } = useSortable("severity");
  const rows = sort(filtered, (f, key) =>
    key === "severity" ? SEV_RANK[f.severity] ?? 0 : key === "asset" ? (assetNames[f.asset_key] || "") : f[key]);

  const act = (f, action) => {
    setActionErr(null);
    (action === "dismiss" ? dismissFinding(f.id) : resolveFinding(f.id))
      .then(() => onAction())
      .catch((e) => setActionErr(e.message));
  };

  if (loading) return <div style={{ padding: "40px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 13 }}>Loading…</div>;
  if (findings.length === 0) return (
    capabilitiesTotal > 0
      ? <EmptyState title="Capabilities detected. No open findings yet." />
      : <EmptyState title="No findings."
          hint="Run Intelligence after ingesting OTel traces — findings are normalized signals across security, performance, operations, dependency, and inventory." />
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start", flexWrap: "wrap" }}>
        <SearchBox query={query} onChange={setQuery} placeholder="Search findings…" count={filtered.length} total={visible.length} />
        <FilterSelect value={assetFilter}  onChange={setAssetFilter}  options={assetOptions} allLabel="All assets" />
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
              <SortableTh label="Asset"     sortKey="asset"     active={sortKey === "asset"}     dir={sortDir} onToggle={toggle} />
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
                  <td style={{ padding: "10px 8px", fontSize: 12, color: T.text, fontFamily: FONT_MONO }}>{assetNames[f.asset_key] || "—"}</td>
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
                    <td colSpan={canAct ? 7 : 6} style={{ padding: "14px 18px", background: T.panelHi }}>
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

  const [tab, setTab] = useState("systems");
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
      fetchIntelligenceAssetSummary(),
      fetchIntelligenceCapabilities(),
      fetchIntelligenceFindings(),
    ])
      .then(([summary, c, f]) => {
        setAssets(summary.assets || []);
        setCapabilities(c);
        setFindings(f);
      })
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

  const handleFindingAction = (f, action) => {
    (action === "dismiss" ? dismissFinding(f.id) : resolveFinding(f.id))
      .then(() => load())
      .catch((e) => setError(e.message));
  };

  const assetNames = useMemo(
    () => Object.fromEntries(assets.map((a) => [a.asset_key, a.asset_name])),
    [assets]
  );

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
        subtitle="What each AI system can do, and what its observed behavior means — grouped by AI system"
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
          <TabButton active={tab === "systems"}      onClick={() => setTab("systems")}      count={assets.length}>AI Systems</TabButton>
          <TabButton active={tab === "capabilities"} onClick={() => setTab("capabilities")} count={capabilities.length}>Capabilities</TabButton>
          <TabButton active={tab === "findings"}     onClick={() => setTab("findings")}     count={openFindings.length}>Findings</TabButton>
        </div>

        {tab === "systems" && (
          <AISystemsTab assets={assets} capabilitiesTotal={capabilities.length} loading={loading}
            canAct={canAct} onFindingAction={handleFindingAction} />
        )}
        {tab === "capabilities" && (
          <CapabilitiesTab capabilities={capabilities} assetNames={assetNames} loading={loading} />
        )}
        {tab === "findings" && (
          <FindingsTab findings={findings} assetNames={assetNames} capabilitiesTotal={capabilities.length}
            loading={loading} canAct={canAct} onAction={load} />
        )}
      </Card>
    </div>
  );
}
