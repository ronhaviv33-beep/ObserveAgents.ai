import React, { useState, useCallback, useEffect } from "react";
import { authFetch, BASE } from "../api.js";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { Card, Pill, useSortable, useSearch, SearchBox, SortableTh } from "./ui.jsx";
import { useUser, useRoles, canSeePage } from "../auth.jsx";
import { MODELS, parseUTC } from "../data/demoData.js";

function AuditLogTable({ audit, hasMore = false, loadingMore = false, onLoadMore }) {
  const [expanded, setExpanded] = useState(null);
  const { sortKey, sortDir, toggle: sortToggle, sort } = useSortable("timestamp");

  const toggleExpand = (id) => setExpanded(prev => prev === id ? null : id);

  const colKey = { "Time":"timestamp","Team":"team","Agent":"agent","Model":"model","Status":"blocked","Flags":"sensitive","Tokens":"total_tokens","Cost":"cost_usd" };

  // Build a lookup: agent → sorted timestamps, for loop detection per-row
  const agentTimes = React.useMemo(() => {
    const m = {};
    audit.forEach(r => { (m[r.agent] = m[r.agent] || []).push(parseUTC(r.timestamp).getTime()); });
    Object.values(m).forEach(a => a.sort((x,y) => x - y));
    return m;
  }, [audit]);
  const isLoopRow = (r) => {
    const times = agentTimes[r.agent] || [];
    const t = parseUTC(r.timestamp).getTime();
    const nearby = times.filter(x => Math.abs(x - t) < 5 * 60 * 1000);
    return nearby.length >= 5;
  };
  const isAfterHours = (r) => { const h = parseUTC(r.timestamp).getHours(); return h < 7 || h >= 20; };
  const sorted = sort(audit, (r, k) => {
    if (k === "timestamp") return parseUTC(r.timestamp).getTime();
    if (k === "blocked")   return r.blocked ? 1 : 0;
    if (k === "sensitive") return r.sensitive ? 1 : 0;
    return r[k];
  });
  const { query, setQuery, filtered } = useSearch(sorted, r =>
    `${r.team} ${r.agent} ${r.model} ${r.prompt||""} ${r.block_reason||""}`
  );

  return (
    <Card title="Audit Log" subtitle="All requests — including blocked and sensitive-flagged. Click a row for full details.">
      <SearchBox query={query} onChange={setQuery} placeholder="Search team, agent, model, prompt…" count={filtered.length} total={audit.length} />
      <table style={{ width:"100%", borderCollapse:"collapse" }}>
        <thead>
          <tr style={{ borderBottom:`1px solid ${T.border}` }}>
            {["Time","Team","Agent","Model","Status","Flags","Tokens","Cost",""].map((h) => h === "" ? (
              <th key={h} style={{ padding:"10px 8px", width:24 }} />
            ) : (
              <SortableTh key={h} label={h} sortKey={colKey[h]} active={sortKey===colKey[h]} dir={sortDir} onToggle={sortToggle} />
            ))}
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 ? (
            <tr><td colSpan={9} style={{ padding:"20px 8px", color:T.textMute, fontFamily:FONT_MONO, fontSize:13 }}>{audit.length === 0 ? "No audit records yet." : "No records match your search."}</td></tr>
          ) : filtered.map((r) => {
            const isOpen = expanded === r.id;
            const rowBg = r.blocked ? `${T.crit}08` : "transparent";
            let findings = [];
            try { findings = JSON.parse(r.sensitive_findings || "[]"); } catch {}
            return (
              <React.Fragment key={r.id}>
                <tr style={{ borderBottom: isOpen ? "none" : `1px solid ${T.border}`, background: rowBg, cursor:"pointer" }}
                    onClick={() => toggleExpand(r.id)}>
                  <td style={{ padding:"10px 8px", fontFamily:FONT_MONO, fontSize:11, color:T.textMute }}>{parseUTC(r.timestamp).toLocaleString("en-US")}</td>
                  <td style={{ padding:"10px 8px", fontSize:12, color:T.text }}>{r.team}</td>
                  <td style={{ padding:"10px 8px", fontSize:12, color:T.textDim }}>{r.agent}</td>
                  <td style={{ padding:"10px 8px", fontFamily:FONT_MONO, fontSize:11, color:T.textDim }}>{r.model}</td>
                  <td style={{ padding:"10px 8px" }}>
                    {r.blocked ? <Pill color={T.crit}>blocked</Pill> : <Pill color={T.accent}>ok</Pill>}
                  </td>
                  <td style={{ padding:"6px 8px" }}>
                    <div style={{ display:"flex", flexWrap:"wrap", gap:3 }}>
                      {r.pricing_estimated && <Pill color="#f97316">unknown mdl</Pill>}
                      {isLoopRow(r)      && <Pill color="#eab308">loop</Pill>}
                      {isAfterHours(r)   && <Pill color={T.info}>after-hrs</Pill>}
                      {!r.pricing_estimated && !isLoopRow(r) && !isAfterHours(r) && (
                        <span style={{ color:T.textMute, fontFamily:FONT_MONO, fontSize:11 }}>—</span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding:"10px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.textDim }}>{r.total_tokens.toLocaleString()}</td>
                  <td style={{ padding:"10px 8px", fontFamily:FONT_MONO, fontSize:12, color: r.pricing_estimated ? "#f97316" : T.text }}>
                    {r.pricing_estimated && <span title="Conservative estimate — model not in pricing table" style={{ marginRight:2 }}>~</span>}
                    ${r.cost_usd.toFixed(6)}
                  </td>
                  <td style={{ padding:"10px 8px", fontFamily:FONT_MONO, fontSize:10, color: isOpen ? T.accent : T.textMute, userSelect:"none" }}>
                    {isOpen ? "▲" : "▼"}
                  </td>
                </tr>
                {isOpen && (() => {
                  const startTime = parseUTC(r.timestamp);
                  const endTime   = new Date(startTime.getTime() + (r.latency_ms || 0));
                  const afterHrs  = isAfterHours(r);
                  const loopFlag  = isLoopRow(r);
                  const Field = ({ label, value, color, mono = true }) => (
                    <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
                      <div style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>{label}</div>
                      <div style={{ fontSize:12, fontFamily: mono ? FONT_MONO : FONT_UI, color: color || T.text, wordBreak:"break-all" }}>{value ?? "—"}</div>
                    </div>
                  );
                  return (
                    <tr style={{ background: r.blocked ? `${T.crit}06` : T.panelHi }}>
                      <td colSpan={9} style={{ borderBottom:`1px solid ${T.border}`, padding:0 }}>
                        <div style={{ padding:"20px 24px", display:"flex", flexDirection:"column", gap:18, borderTop:`1px solid ${T.border}` }}>

                          {/* Section header */}
                          <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between" }}>
                            <div style={{ fontSize:11, fontFamily:FONT_MONO, letterSpacing:"0.14em", textTransform:"uppercase", color:T.textDim, fontWeight:600 }}>Request Details</div>
                            <div style={{ display:"flex", gap:6 }}>
                              {r.blocked   && <Pill color={T.crit}>blocked</Pill>}
                              {r.sensitive && <Pill color={T.warn}>Sensitive Content</Pill>}
                              {loopFlag    && <Pill color="#eab308">loop</Pill>}
                              {afterHrs    && <Pill color={T.info}>after-hrs</Pill>}
                              {r.pricing_estimated && <Pill color="#f97316">est. pricing</Pill>}
                            </div>
                          </div>

                          {/* Identity grid */}
                          <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:12, background:T.panel, border:`1px solid ${T.border}`, borderRadius:8, padding:"14px 16px" }}>
                            <Field label="Request ID"  value={`#${r.id}`}                              color={T.textDim} />
                            <Field label="Team"        value={r.team}                                  color={T.text} />
                            <Field label="Agent"       value={r.agent}                                 color={T.text} />
                            <Field label="Model"       value={r.model}                                 color={T.text} />
                            <Field label="Status"      value={r.blocked ? "BLOCKED" : "OK"}            color={r.blocked ? T.crit : T.accent} />
                            <Field label="Latency"     value={`${Math.round(r.latency_ms || 0)} ms`}   color={T.text} />
                          </div>

                          {/* Timing + tokens + cost grid */}
                          <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:12, background:T.panel, border:`1px solid ${T.border}`, borderRadius:8, padding:"14px 16px" }}>
                            <Field label="Start Time"         value={startTime.toLocaleTimeString("en-US")}                        color={T.text} />
                            <Field label="End Time"           value={endTime.toLocaleTimeString("en-US")}                          color={T.text} />
                            <Field label="Total Tokens"       value={(r.total_tokens || 0).toLocaleString()}                color={T.text} />
                            <Field label="Prompt Tokens"      value={(r.prompt_tokens || 0).toLocaleString()}               color={T.text} />
                            <Field label="Completion Tokens"  value={(r.completion_tokens || 0).toLocaleString()}           color={T.text} />
                            <Field label="Spend"
                              value={`${r.pricing_estimated === true ? "~" : ""}$${(r.cost_usd || 0).toFixed(6)}`}
                              color={r.pricing_estimated === true ? "#f97316" : T.text} />
                          </div>

                          {/* Prompt */}
                          <div>
                            <div style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.14em", textTransform:"uppercase", color:T.info, marginBottom:8 }}>Prompt</div>
                            <div style={{ background:T.bg, border:`1px solid ${T.border}`, borderRadius:6, padding:"12px 16px", fontFamily:FONT_MONO, fontSize:12, color:T.text, lineHeight:1.7, whiteSpace:"pre-wrap", wordBreak:"break-word", maxHeight:180, overflowY:"auto" }}>
                              {r.prompt || <span style={{ color:T.textMute }}>—</span>}
                            </div>
                          </div>

                          {/* Block reason OR Response */}
                          {r.blocked ? (
                            <div>
                              <div style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.14em", textTransform:"uppercase", color:T.crit, marginBottom:8 }}>Block Reason</div>
                              <div style={{ background:`${T.crit}10`, border:`1px solid ${T.crit}33`, borderRadius:6, padding:"12px 16px", fontFamily:FONT_MONO, fontSize:12, color:T.crit, lineHeight:1.6 }}>
                                {r.block_reason || "—"}
                              </div>
                            </div>
                          ) : r.response ? (
                            <div>
                              <div style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.14em", textTransform:"uppercase", color:T.accent, marginBottom:8 }}>Response</div>
                              <div style={{ background:T.bg, border:`1px solid ${T.border}`, borderRadius:6, padding:"12px 16px", fontFamily:FONT_MONO, fontSize:12, color:T.text, lineHeight:1.7, whiteSpace:"pre-wrap", wordBreak:"break-word", maxHeight:180, overflowY:"auto" }}>
                                {r.response}
                              </div>
                            </div>
                          ) : null}

                          {/* Security findings */}
                          {findings.length > 0 && (
                            <div>
                              <div style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.14em", textTransform:"uppercase", color:T.warn, marginBottom:8 }}>
                                Security Findings ({findings.length})
                              </div>
                              <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                                {findings.map((f, i) => (
                                  <div key={i} style={{ display:"grid", gridTemplateColumns:"90px 160px 1fr", alignItems:"center", gap:12, padding:"8px 14px", background:T.bg, border:`1px solid ${T.border}`, borderLeft:`3px solid ${f.severity==="critical"?T.crit:T.warn}`, borderRadius:4 }}>
                                    <Pill color={f.severity==="critical"?T.crit:T.warn}>{f.severity}</Pill>
                                    <span style={{ fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{f.type}</span>
                                    <span style={{ fontFamily:FONT_MONO, fontSize:11, color:T.textMute }}>{f.sample}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                        </div>
                      </td>
                    </tr>
                  );
                })()}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
      {(hasMore || loadingMore) && (
        <div style={{ marginTop:14, textAlign:"center" }}>
          <button onClick={onLoadMore} disabled={loadingMore}
            style={{ background:"transparent", border:`1px solid ${T.border}`, color:T.textDim, padding:"8px 24px", borderRadius:4, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer", letterSpacing:"0.08em", textTransform:"uppercase", opacity:loadingMore?0.5:1 }}>
            {loadingMore ? "Loading…" : `Load more (50 at a time)`}
          </button>
        </div>
      )}
    </Card>
  );
}

export default function SecurityPage() {
  const currentUser = useUser();
  const roles = useRoles();
  const isAdmin = canSeePage(currentUser, "settings", roles);

  const [alerts,    setAlerts]    = useState([]);
  const [policies,      setPolicies]      = useState([]);
  const [audit,         setAudit]         = useState([]);
  const [auditOffset,   setAuditOffset]   = useState(0);
  const [auditHasMore,  setAuditHasMore]  = useState(false);
  const [auditLoading,  setAuditLoading]  = useState(false);
  const AUDIT_PAGE = 50;
  const [pForm,     setPForm]     = useState({ team:"", rule_type:"block_model", value:"*" });
  const [saving,    setSaving]    = useState(false);
  const [loading,   setLoading]   = useState(true);
  const [alertsOpen, setAlertsOpen] = useState(false);

  const loadAudit = useCallback(async (offset = 0, append = false) => {
    if (!isAdmin) return;
    setAuditLoading(true);
    try {
      const r = await authFetch(`${BASE}/audit?sensitive_only=false&blocked_only=false&limit=${AUDIT_PAGE + 1}&skip=${offset}`);
      if (!r?.ok) return;
      const rows = await r.json();
      const hasMore = rows.length > AUDIT_PAGE;
      const page = rows.slice(0, AUDIT_PAGE);
      setAudit(prev => append ? [...prev, ...page] : page);
      setAuditHasMore(hasMore);
      setAuditOffset(offset + AUDIT_PAGE);
    } catch { /* ignore */ }
    finally { setAuditLoading(false); }
  }, [isAdmin]);

  const load = useCallback(async () => {
    try {
      const fetchers = [
        authFetch(`${BASE}/security/alerts`).then((x) => x.json()),
      ];
      if (isAdmin) {
        fetchers.push(
          authFetch(`${BASE}/policies`).then((x) => x.json()),
        );
      }
      const [a, p] = await Promise.all(fetchers);
      setAlerts(a);
      if (p) setPolicies(p);
      if (isAdmin) await loadAudit(0, false);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [isAdmin, loadAudit]);

  useEffect(() => { load(); }, [load]);

  const handleCreatePolicy = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await authFetch(`${BASE}/policies`, {
        method: "POST",
        body: JSON.stringify(pForm),
      });
      setPForm({ team:"", rule_type:"block_model", value:"*" });
      await load();
    } finally { setSaving(false); }
  };

  const handleDeletePolicy = async (id) => {
    await authFetch(`${BASE}/policies/${id}`, { method:"DELETE" });
    await load();
  };

  const sevColor = (s) => s==="critical"?T.crit:s==="high"?T.warn:s==="medium"?T.info:T.textDim;
  const alertColor = (s) => s==="critical"?T.crit:s==="warning"?T.warn:T.info;

  if (loading) return <div style={{ color:T.textDim, fontFamily:FONT_MONO, padding:24 }}>Loading security data…</div>;

  const blockedCount   = audit.filter((r) => r.blocked).length;

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:14 }}>

      {/* KPI strip */}
      {(() => {
        const kpis = [
          { label:"Live Alerts",    value:alerts.length,   color:alerts.length>0?T.crit:T.accent },
          ...(isAdmin ? [
            { label:"Policy Rules",   value:policies.length, color:T.info },
            { label:"Blocked Reqs",   value:blockedCount,    color:blockedCount>0?T.crit:T.accent },
          ] : []),
        ];
        return (
          <div style={{ display:"grid", gridTemplateColumns:`repeat(${kpis.length},1fr)`, gap:12 }}>
            {kpis.map((k) => (
              <div key={k.label} style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:8, padding:16 }}>
                <div style={{ fontSize:10, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textDim }}>{k.label}</div>
                <div style={{ fontSize:32, fontFamily:FONT_MONO, fontWeight:500, color:k.color, marginTop:8, lineHeight:1 }}>{k.value}</div>
              </div>
            ))}
          </div>
        );
      })()}

      {/* Live alerts — collapsible */}
      <div style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:6, overflow:"hidden" }}>
        <button
          onClick={() => setAlertsOpen(o => !o)}
          style={{ width:"100%", display:"flex", alignItems:"center", justifyContent:"space-between", padding:"14px 18px", background:"transparent", border:"none", cursor:"pointer", textAlign:"left" }}
        >
          <div>
            <div style={{ fontSize:11, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textDim, fontFamily:FONT_MONO, fontWeight:500 }}>
              Live Security Alerts
              {alerts.length > 0 && (
                <span style={{ marginLeft:8, background:T.crit+"22", color:T.crit, border:`1px solid ${T.crit}44`, borderRadius:4, padding:"1px 7px", fontSize:10 }}>
                  {alerts.length}
                </span>
              )}
            </div>
            <div style={{ fontSize:13, color:T.textMute, marginTop:4, fontFamily:FONT_MONO }}>Detected from real telemetry data</div>
          </div>
          <span style={{ color:T.textDim, fontSize:16, transition:"transform 0.2s", transform:alertsOpen?"rotate(180deg)":"rotate(0deg)", display:"block" }}>▾</span>
        </button>

        {alertsOpen && (
          <div style={{ padding:"0 18px 18px" }}>
            {alerts.length === 0 ? (
              <div style={{ color:T.accent, fontFamily:FONT_MONO, fontSize:13, padding:"16px 0" }}>✓ No security alerts detected</div>
            ) : (
              <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                {alerts.map((a, i) => (
                  <div key={i} style={{ padding:"12px 14px", background:T.panelHi, borderLeft:`2px solid ${alertColor(a.sev)}`, borderRadius:4 }}>
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
                      <div>
                        <div style={{ fontFamily:FONT_MONO, fontSize:10, color:alertColor(a.sev), letterSpacing:"0.08em", textTransform:"uppercase", marginBottom:4 }}>{a.type}</div>
                        <div style={{ fontSize:13, color:T.text }}>{a.msg}</div>
                        <div style={{ fontSize:11, color:T.textMute, marginTop:4 }}>Agent: {a.entity} · {a.action}</div>
                      </div>
                      <Pill color={alertColor(a.sev)}>{a.sev}</Pill>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Operational Risk Overview */}
      <div style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:8, padding:"20px 24px" }}>
        <div style={{ fontSize:13, fontWeight:600, color:T.text, letterSpacing:"-0.01em", marginBottom:4 }}>Operational Risk Overview</div>
        <div style={{ fontSize:12, color:T.textMute, marginBottom:16 }}>
          Monitor policy violations, unmanaged AI assets, blocked requests, runtime anomalies, and governance events across your AI operations.
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(180px, 1fr))", gap:12 }}>
          {[
            { label:"Live Alerts",    value:alerts.length,                                         color:alerts.length>0?T.crit:T.accent,   note:"Active findings" },
            { label:"Policy Rules",   value:policies.length,                                        color:T.info,                            note:"Active only in enforce guard mode" },
            { label:"Blocked Reqs",  value:blockedCount,                                           color:blockedCount>0?T.crit:T.accent,    note:"Last 50 audited" },
            { label:"Critical Alerts", value:alerts.filter(a=>a.sev==="critical").length,          color:T.crit,                            note:"Require immediate review" },
            { label:"Warning Alerts", value:alerts.filter(a=>a.sev==="warning").length,            color:T.warn,                            note:"Monitor closely" },
          ].map(({ label, value, color, note }) => (
            <div key={label} style={{ background:T.panelHi, border:`1px solid ${T.border}`, borderRadius:6, padding:"14px 16px" }}>
              <div style={{ fontSize:9, fontFamily:FONT_MONO, color:T.textMute, letterSpacing:"0.12em", textTransform:"uppercase", marginBottom:8 }}>{label}</div>
              <div style={{ fontSize:26, fontWeight:700, color, letterSpacing:"-0.02em", lineHeight:1 }}>{value}</div>
              <div style={{ fontSize:10, color:T.textMute, fontFamily:FONT_MONO, marginTop:6 }}>{note}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Policy rules — admin only */}
      {isAdmin && <Card title="Model Policy Rules" subtitle="Control which models each team is allowed to use. Team must match exactly what's sent in chat requests.">
        <form onSubmit={handleCreatePolicy} style={{ display:"flex", gap:10, flexWrap:"wrap", alignItems:"flex-end", marginBottom:16 }}>
          <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
            <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>Team * <span style={{ color:T.textMute, textTransform:"none", fontSize:9 }}>(or * for all)</span></label>
            <input value={pForm.team} onChange={(e) => setPForm({...pForm,team:e.target.value})}
              placeholder="e.g. SOC or *" required
              style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"6px 10px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, width:160 }}
            />
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
            <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>Model *</label>
            <select value={pForm.value} onChange={(e) => setPForm({...pForm,value:e.target.value})}
              style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"6px 10px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, minWidth:200 }}>
              <option value="*">* (all models)</option>
              {MODELS.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
            </select>
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
            <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>Rule Type</label>
            <select value={pForm.rule_type} onChange={(e) => setPForm({...pForm,rule_type:e.target.value})}
              style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"6px 10px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, minWidth:150 }}>
              <option value="block_model">Block model</option>
              <option value="allow_model">Allow model (allowlist)</option>
            </select>
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:4, alignSelf:"flex-end" }}>
            <div style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.08em", color: pForm.rule_type==="block_model" ? T.crit : T.accent, marginBottom:8 }}>
              {pForm.rule_type==="block_model"
                ? `⊘ Will BLOCK "${pForm.value}" for team "${pForm.team}" (enforce mode only — advisory otherwise)`
                : `✓ Will ALLOW only "${pForm.value}" for team "${pForm.team}" (enforce mode only — advisory otherwise)`}
            </div>
          </div>
          <button type="submit" disabled={saving}
            style={{ background: pForm.rule_type==="block_model" ? T.crit : T.accent, color: pForm.rule_type==="block_model" ? "#fff" : T.bg, border:"none", padding:"8px 18px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, fontWeight:600, cursor:"pointer", opacity:saving?0.6:1 }}>
            {saving ? "Saving…" : "+ Add Policy"}
          </button>
        </form>

        {policies.length === 0 ? (
          <div style={{ color:T.textMute, fontFamily:FONT_MONO, fontSize:13, padding:"8px 0" }}>No policy rules configured. Add one above.</div>
        ) : (
          <table style={{ width:"100%", borderCollapse:"collapse" }}>
            <thead>
              <tr style={{ borderBottom:`1px solid ${T.border}` }}>
                {["Team","Rule Type","Model","Created",""].map((h) => (
                  <th key={h} style={{ textAlign:"left", padding:"10px 8px", fontFamily:FONT_MONO, fontSize:10, letterSpacing:"0.1em", textTransform:"uppercase", color:T.textDim, fontWeight:500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {policies.map((r) => (
                <tr key={r.id} style={{ borderBottom:`1px solid ${T.border}` }}>
                  <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{r.team}</td>
                  <td style={{ padding:"12px 8px" }}><Pill color={r.rule_type==="block_model"?T.crit:T.accent}>{r.rule_type}</Pill></td>
                  <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{r.value}</td>
                  <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:11, color:T.textMute }}>{new Date(r.created_at).toLocaleDateString("en-US")}</td>
                  <td style={{ padding:"12px 8px" }}>
                    <button onClick={() => handleDeletePolicy(r.id)}
                      style={{ background:"transparent", border:`1px solid ${T.border}`, color:T.crit, padding:"4px 10px", borderRadius:3, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer" }}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>}

      {/* Audit log — admin only */}
      {isAdmin && <AuditLogTable audit={audit} hasMore={auditHasMore} loadingMore={auditLoading} onLoadMore={() => loadAudit(auditOffset, true)} />}
    </div>
  );
}
