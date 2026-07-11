import React, { useState } from "react";
import { T, FONT_UI, FONT_MONO } from "../theme.js";

export const Card = ({ children, style, title, subtitle, right }) => (
  <div style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:16, padding:24, boxShadow:T.shadow, ...style }}>
    {(title||right) && (
      <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", marginBottom:16 }}>
        <div>
          {title    && <div style={{ fontSize:14, color:T.text, fontFamily:FONT_UI, fontWeight:600, letterSpacing:"-0.01em" }}>{title}</div>}
          {subtitle && <div style={{ fontSize:13, color:T.textMute, marginTop:4, lineHeight:1.5 }}>{subtitle}</div>}
        </div>
        {right}
      </div>
    )}
    {children}
  </div>
);

export const Stat = ({ label, value, delta, suffix, accent }) => (
  <Card style={{ padding:22 }}>
    <div style={{ fontSize:12.5, color:T.textDim, fontFamily:FONT_UI, fontWeight:500, letterSpacing:0 }}>{label}</div>
    <div style={{ fontSize:32, fontFamily:FONT_UI, fontWeight:650, color:accent||T.text, marginTop:12, letterSpacing:"-0.03em", lineHeight:1, fontVariantNumeric:"tabular-nums" }}>
      {value}{suffix && <span style={{ fontSize:14, color:T.textMute, marginLeft:5, fontWeight:500 }}>{suffix}</span>}
    </div>
    {delta && (
      <div style={{ fontSize:12.5, marginTop:10, fontWeight:500, display:"inline-flex", alignItems:"center", gap:5, color:delta.startsWith("+")?T.crit:T.ok }}>
        <span style={{ fontVariantNumeric:"tabular-nums" }}>{delta}</span>
        <span style={{ color:T.textMute, fontWeight:400 }}>vs yesterday</span>
      </div>
    )}
  </Card>
);

export const Pill = ({ children, color }) => (
  <span style={{ display:"inline-flex", alignItems:"center", gap:5, padding:"3px 9px", borderRadius:999, fontSize:11.5, fontFamily:FONT_UI, fontWeight:600, letterSpacing:0, textTransform:"none", background:`${color}14`, color, border:`1px solid ${color}2E` }}>
    <span style={{ width:6, height:6, borderRadius:999, background:color, flexShrink:0 }} />
    {children}
  </span>
);

export const sevColor = (s) => s==="critical"?T.crit:s==="warning"?T.warn:T.info;
export const fmt$  = (n) => n>=1000?`$${(n/1000).toFixed(2)}k`:`$${n.toFixed(2)}`;
export const fmtK  = (n) => n>=1_000_000?`${(n/1_000_000).toFixed(2)}M`:n>=1000?`${(n/1000).toFixed(1)}k`:n.toString();
export const fmtTime=(ts)=>{ const d=Date.now()-ts; if(d<60_000)return"just now"; if(d<3_600_000)return`${Math.floor(d/60_000)}m ago`; if(d<86_400_000)return`${Math.floor(d/3_600_000)}h ago`; return new Date(ts).toLocaleDateString("en-US"); };

export function useSortable(defaultKey, defaultDir = "desc") {
  const [sortKey, setSortKey] = useState(defaultKey);
  const [sortDir, setSortDir] = useState(defaultDir);
  const toggle = (key) => {
    if (key === sortKey) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  };
  const sort = (rows, getValue) => [...rows].sort((a, b) => {
    const va = getValue(a, sortKey), vb = getValue(b, sortKey);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    const cmp = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return sortDir === "asc" ? cmp : -cmp;
  });
  return { sortKey, sortDir, toggle, sort };
}

export const SortableTh = ({ label, sortKey, active, dir, onToggle, style: extraStyle = {} }) => (
  <th onClick={() => onToggle(sortKey)}
    style={{ textAlign:"left", padding:"11px 12px", fontFamily:FONT_UI, fontSize:11.5, letterSpacing:"0.04em",
      textTransform:"uppercase", color: active ? T.text : T.textMute, fontWeight:600,
      background:T.panelHi, borderBottom:`1px solid ${T.border}`,
      cursor:"pointer", userSelect:"none", whiteSpace:"nowrap", ...extraStyle }}
    title={`Sort by ${label}`}>
    {label}
    <span style={{ marginLeft:5, opacity: active ? 1 : 0.35, fontSize:9 }}>
      {active ? (dir === "asc" ? "▲" : "▼") : "⇅"}
    </span>
  </th>
);

export function useSearch(rows, getSearchString) {
  const [query, setQuery] = useState("");
  const filtered = query.trim()
    ? rows.filter(r => getSearchString(r).toLowerCase().includes(query.toLowerCase().trim()))
    : rows;
  return { query, setQuery, filtered };
}

export const SearchBox = ({ query, onChange, placeholder = "Search…", count, total }) => (
  <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:12 }}>
    <div style={{ position:"relative", flex:1, maxWidth:360 }}>
      <span style={{ position:"absolute", left:12, top:"50%", transform:"translateY(-50%)", color:T.textMute, fontSize:14, pointerEvents:"none" }}>⌕</span>
      <input
        value={query}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        style={{ width:"100%", boxSizing:"border-box", background:T.panel, color:T.text, border:`1px solid ${query ? T.accent : T.border}`,
          boxShadow: query ? "0 0 0 3px rgba(37,99,235,0.12)" : T.shadow,
          padding:"9px 12px 9px 34px", borderRadius:10, fontSize:13.5, fontFamily:FONT_UI, outline:"none", transition:"border-color .15s ease, box-shadow .15s ease" }}
      />
      {query && (
        <button onClick={() => onChange("")}
          style={{ position:"absolute", right:8, top:"50%", transform:"translateY(-50%)", background:"none", border:"none", color:T.textMute, cursor:"pointer", fontSize:16, lineHeight:1, padding:0 }}>
          ×
        </button>
      )}
    </div>
    {query && (
      <span style={{ fontFamily:FONT_UI, fontSize:12.5, color:T.textMute, fontVariantNumeric:"tabular-nums" }}>
        {count} of {total}
      </span>
    )}
  </div>
);
