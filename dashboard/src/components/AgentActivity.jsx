import React from "react";
import { T, FONT_MONO } from "../theme.js";
import { Card, SearchBox, SortableTh, useSortable, useSearch, Pill, fmt$, fmtK, fmtTime } from "./ui.jsx";

function AgentActivity({ events, allAgents, allTeams }) {
  const { sortKey, sortDir, toggle, sort } = useSortable("cost");
  const baseRows = allAgents.map((a)=>{
    const aev = events.filter((e)=>e.agent===a.id);
    const requests = aev.length;
    const cost     = aev.reduce((s,e)=>s+e.cost,0);
    const avgLat   = requests>0 ? aev.reduce((s,e)=>s+e.latency,0)/requests : 0;
    const errors   = aev.filter((e)=>e.status==="failed").length;
    const last     = aev[0]?.ts||0;
    const teamName = allTeams.find((t)=>t.id===a.team)?.name||a.team;
    return { ...a, requests, cost, avgLat, errors, last, teamName };
  });
  const colKey = { "Agent":"name","Team":"teamName","Requests":"requests","Cost":"cost","Avg latency":"avgLat","Errors":"errors","Last activity":"last" };
  const sorted = sort(baseRows, (r, k) => r[k]);
  const { query, setQuery, filtered: rows } = useSearch(sorted, r => `${r.name} ${r.teamName} ${r.id}`);
  return (
    <Card title="Agents" subtitle="Live runtime activity">
      <SearchBox query={query} onChange={setQuery} placeholder="Search agents or teams…" count={rows.length} total={baseRows.length} />
      <table style={{ width:"100%", borderCollapse:"collapse" }}>
        <thead>
          <tr style={{ borderBottom:`1px solid ${T.border}` }}>
            {["Agent","Team","Requests","Cost","Avg latency","Errors","Last activity"].map((h)=>(
              <SortableTh key={h} label={h} sortKey={colKey[h]} active={sortKey===colKey[h]} dir={sortDir} onToggle={toggle} />
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r)=>(
            <tr key={r.id} style={{ borderBottom:`1px solid ${T.border}` }}>
              <td style={{ padding:"12px 8px" }}>
                <div style={{ fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{r.name}</div>
                <div style={{ fontFamily:FONT_MONO, fontSize:10, color:T.textMute, marginTop:2 }}>{r.id}</div>
              </td>
              <td style={{ padding:"12px 8px", fontSize:12, color:T.textDim }}>{r.teamName}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{r.requests.toLocaleString()}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{fmt$(r.cost)}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:r.avgLat>2000?T.warn:T.textDim }}>{Math.round(r.avgLat)}ms</td>
              <td style={{ padding:"12px 8px" }}>{r.errors>10?<Pill color={T.crit}>{r.errors}</Pill>:r.errors>0?<Pill color={T.warn}>{r.errors}</Pill>:<span style={{ fontFamily:FONT_MONO, fontSize:12, color:T.textMute }}>0</span>}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.textDim }}>{fmtTime(r.last)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export default AgentActivity;
