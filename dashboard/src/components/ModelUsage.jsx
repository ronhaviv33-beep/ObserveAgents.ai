import React from "react";
import { T, FONT_MONO } from "../theme.js";
import { Card, SearchBox, SortableTh, useSortable, useSearch, Pill, fmt$, fmtK } from "./ui.jsx";
import { MODELS, providerFromModel, tierFromModel, approvedModel } from "../data/demoData.js";

function ModelUsage({ A }) {
  const { sortKey, sortDir, toggle, sort } = useSortable("cost");
  const allModelNames = [...new Set([...MODELS.map((m)=>m.name), ...Object.keys(A.costByModel)])];
  const baseRows = allModelNames.map((name)=>{
    const meta = MODELS.find((m)=>m.name===name);
    const cost  = A.costByModel[name]||0;
    const tokens= A.tokensByModel[name]||0;
    const lats  = A.latencyByModel[name]||[];
    const avgLat= lats.length>0 ? lats.reduce((s,x)=>s+x,0)/lats.length : 0;
    const p95   = lats.length>0 ? [...lats].sort((a,b)=>a-b)[Math.floor(lats.length*0.95)] : 0;
    return { name, provider:meta?.provider||providerFromModel(name), tier:meta?.tier||tierFromModel(name), approved:meta?.approved??approvedModel(name), cost, tokens, avgLat, p95, calls:lats.length };
  });
  const colKey = { "Model":"name","Provider":"provider","Tier":"tier","Approved":"approved","Calls":"calls","Tokens":"tokens","Cost":"cost","Avg latency":"avgLat","p95":"p95" };
  const sorted = sort(baseRows, (r, k) => r[k]);
  const { query, setQuery, filtered: modelRows } = useSearch(sorted, r => `${r.name} ${r.provider} ${r.tier}`);
  return (
    <Card title="Models" subtitle="Performance, spend, and governance posture">
      <SearchBox query={query} onChange={setQuery} placeholder="Search models or providers…" count={modelRows.length} total={baseRows.length} />
      <table style={{ width:"100%", borderCollapse:"collapse" }}>
        <thead>
          <tr style={{ borderBottom:`1px solid ${T.border}` }}>
            {["Model","Provider","Tier","Approved","Calls","Tokens","Cost","Avg latency","p95"].map((h)=>(
              <SortableTh key={h} label={h} sortKey={colKey[h]} active={sortKey===colKey[h]} dir={sortDir} onToggle={toggle} />
            ))}
          </tr>
        </thead>
        <tbody>
          {modelRows.map((m)=>(
            <tr key={m.name} style={{ borderBottom:`1px solid ${T.border}` }}>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{m.name}</td>
              <td style={{ padding:"12px 8px", fontSize:12, color:T.textDim }}>{m.provider}</td>
              <td style={{ padding:"12px 8px" }}><Pill color={m.tier==="premium"?T.warn:m.tier==="mid"?T.info:T.accent}>{m.tier}</Pill></td>
              <td style={{ padding:"12px 8px" }}>{m.approved?<Pill color={T.accent}>yes</Pill>:<Pill color={T.crit}>no</Pill>}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{m.calls.toLocaleString()}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{fmtK(m.tokens)}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{fmt$(m.cost)}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.textDim }}>{Math.round(m.avgLat)}ms</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:m.p95>3000?T.warn:T.textDim }}>{Math.round(m.p95)}ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export default ModelUsage;
