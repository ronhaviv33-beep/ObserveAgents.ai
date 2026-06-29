import React, { useState, useCallback, useEffect } from "react";
import { authFetch, BASE } from "../api.js";
import { T, FONT_MONO } from "../theme.js";
import { Card, Pill, useSortable, useSearch, SearchBox, SortableTh } from "./ui.jsx";

function SortableBudgetTable({ rules, onDelete }) {
  const { sortKey, sortDir, toggle, sort } = useSortable("created_at");
  const colKey = { "Team":"team","Agent":"agent","Limit":"limit_usd","Period":"period","Action":"action","Created":"created_at" };
  const sorted = sort(rules, (r, k) => {
    if (k === "created_at") return new Date(r.created_at).getTime();
    if (k === "limit_usd")  return r.limit_usd;
    return r[k] || "";
  });
  const { query, setQuery, filtered } = useSearch(sorted, r => `${r.team} ${r.agent||""} ${r.period} ${r.action}`);
  return (
    <>
    <SearchBox query={query} onChange={setQuery} placeholder="Search team, agent, period…" count={filtered.length} total={rules.length} />
    <table style={{ width:"100%", borderCollapse:"collapse" }}>
      <thead>
        <tr style={{ borderBottom:`1px solid ${T.border}` }}>
          {["Team","Agent","Limit","Period","Action","Created",""].map((h) => h === "" ? (
            <th key={h} style={{ padding:"10px 8px" }} />
          ) : (
            <SortableTh key={h} label={h} sortKey={colKey[h]} active={sortKey===colKey[h]} dir={sortDir} onToggle={toggle} />
          ))}
        </tr>
      </thead>
      <tbody>
        {filtered.map((r) => (
          <tr key={r.id} style={{ borderBottom:`1px solid ${T.border}` }}>
            <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{r.team}</td>
            <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.textDim }}>{r.agent||<span style={{color:T.textMute}}>all agents</span>}</td>
            <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.accent }}>${r.limit_usd}</td>
            <td style={{ padding:"12px 8px" }}><Pill color={T.info}>{r.period}</Pill></td>
            <td style={{ padding:"12px 8px" }}><Pill color={r.action==="block"?T.crit:T.warn}>{r.action}</Pill></td>
            <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:11, color:T.textMute }}>{new Date(r.created_at).toLocaleDateString()}</td>
            <td style={{ padding:"12px 8px" }}>
              <button onClick={() => onDelete(r.id)}
                style={{ background:"transparent", border:`1px solid ${T.border}`, color:T.crit, padding:"4px 10px", borderRadius:3, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer" }}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </>
  );
}

export default function BudgetsPage() {
  const [rules,    setRules]    = useState([]);
  const [status,   setStatus]   = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [form,     setForm]     = useState({ team:"", agent:"", limit_usd:"", period:"monthly", action:"alert" });
  const [saving,   setSaving]   = useState(false);
  const [err,      setErr]      = useState(null);

  const load = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([
        authFetch(`${BASE}/budgets`).then((x) => x.json()),
        authFetch(`${BASE}/budgets/status`).then((x) => x.json()).catch(() => []),
      ]);
      setRules(r);
      setStatus(s);
    } catch { /* ignore load errors — show empty state */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      const body = { ...form, limit_usd: parseFloat(form.limit_usd), agent: form.agent || null };
      const r = await authFetch(`${BASE}/budgets`, { method:"POST", body: JSON.stringify(body) });
      if (!r || !r.ok) throw new Error(await r.text());
      setForm({ team:"", agent:"", limit_usd:"", period:"monthly", action:"alert" });
      await load();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    await authFetch(`${BASE}/budgets/${id}`, { method:"DELETE" });
    await load();
  };

  const statusColor = (s) => s==="blocked"?T.crit:s==="warning"?T.warn:T.accent;

  if (loading) return <div style={{ color:T.textDim, fontFamily:FONT_MONO, padding:24 }}>Loading budgets…</div>;

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:14 }}>

      {/* Status cards */}
      {status.length > 0 && (
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))", gap:12 }}>
          {status.map((s) => {
            const c = statusColor(s.status);
            return (
              <div key={s.id} style={{ background:T.panel, border:`1px solid ${s.status==="ok"?T.border:c}`, borderRadius:8, padding:16 }}>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:10 }}>
                  <div>
                    <div style={{ fontFamily:FONT_MONO, fontSize:13, color:T.text }}>{s.team}</div>
                    {s.agent && <div style={{ fontFamily:FONT_MONO, fontSize:11, color:T.textMute, marginTop:2 }}>{s.agent}</div>}
                  </div>
                  <Pill color={c}>{s.status}</Pill>
                </div>
                {/* Progress bar */}
                <div style={{ height:6, background:T.border, borderRadius:3, overflow:"hidden", marginBottom:8 }}>
                  <div style={{ width:`${Math.min(s.pct,100)}%`, height:"100%", background:c, borderRadius:3, transition:"width 0.4s" }}/>
                </div>
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:11, fontFamily:FONT_MONO }}>
                  <span style={{ color:T.textDim }}>${s.spend_usd.toFixed(4)} spent</span>
                  <span style={{ color:T.textMute }}>limit ${s.limit_usd} / {s.period}</span>
                </div>
                <div style={{ fontSize:11, fontFamily:FONT_MONO, color:c, marginTop:4 }}>{s.pct.toFixed(1)}% used · action: {s.action}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add rule form */}
      <Card title="Add Budget Rule" subtitle="Set a spend limit per team or agent">
        <form onSubmit={handleCreate} style={{ display:"flex", gap:10, flexWrap:"wrap", alignItems:"flex-end" }}>
          {[
            { label:"Team *",       key:"team",      placeholder:"e.g. SOC or *" },
            { label:"Agent",        key:"agent",     placeholder:"optional" },
            { label:"Limit (USD) *",key:"limit_usd", placeholder:"e.g. 10.00", type:"number" },
          ].map(({ label, key, placeholder, type }) => (
            <div key={key} style={{ display:"flex", flexDirection:"column", gap:4 }}>
              <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>{label}</label>
              <input
                type={type||"text"} placeholder={placeholder} value={form[key]}
                onChange={(e)=>setForm({...form,[key]:e.target.value})}
                required={label.includes("*")}
                style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"6px 10px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, width:150 }}
              />
            </div>
          ))}
          {[
            { label:"Period", key:"period", options:[["monthly","Monthly"],["daily","Daily"]] },
            { label:"Action", key:"action", options:[["alert","Alert only"],["block","Block requests"]] },
          ].map(({ label, key, options }) => (
            <div key={key} style={{ display:"flex", flexDirection:"column", gap:4 }}>
              <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>{label}</label>
              <select value={form[key]} onChange={(e)=>setForm({...form,[key]:e.target.value})}
                style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"6px 10px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, minWidth:130 }}>
                {options.map(([v,l])=><option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          ))}
          <button type="submit" disabled={saving}
            style={{ background:T.accent, color:T.bg, border:"none", padding:"8px 18px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, fontWeight:600, cursor:"pointer", opacity:saving?0.6:1 }}>
            {saving?"Saving…":"+ Add Rule"}
          </button>
        </form>
        {err && <div style={{ color:T.crit, fontFamily:FONT_MONO, fontSize:12, marginTop:10 }}>{err}</div>}
      </Card>

      {/* Rules table */}
      <Card title="Budget Rules" subtitle={`${rules.length} rule${rules.length===1?"":"s"} configured`}>
        {rules.length === 0 ? (
          <div style={{ color:T.textMute, fontFamily:FONT_MONO, fontSize:13, padding:"20px 0", textAlign:"center" }}>
            No budget rules yet — add one above to start enforcing limits.
          </div>
        ) : (
          <SortableBudgetTable rules={rules} onDelete={handleDelete} />
        )}
      </Card>
    </div>
  );
}
