import React from "react";
import { T, FONT_MONO } from "../theme.js";
import { Card, SearchBox, SortableTh, useSortable, useSearch, Pill, fmt$ } from "./ui.jsx";

function WorkflowHealth({ A, events }) {
  const { sortKey, sortDir, toggle, sort } = useSortable("rate");
  const baseRows = Object.keys(A.callsByWorkflow).map((wf)=>{
    const calls = A.callsByWorkflow[wf];
    const fails = A.failsByWorkflow[wf]||0;
    const cost  = events.filter((e)=>e.workflow===wf).reduce((s,e)=>s+e.cost,0);
    return { wf, calls, fails, rate:fails/calls, cost };
  });
  const colKey = { "Workflow":"wf","Calls":"calls","Failures":"fails","Rate":"rate","Cost":"cost","Status":"rate" };
  const sorted = sort(baseRows, (r, k) => r[k]);
  const { query, setQuery, filtered: rows } = useSearch(sorted, r => r.wf);
  return (
    <Card title="Workflow health" subtitle="Failure rate & spend per workflow">
      <SearchBox query={query} onChange={setQuery} placeholder="Search workflows…" count={rows.length} total={baseRows.length} />
      <table style={{ width:"100%", borderCollapse:"collapse" }}>
        <thead>
          <tr style={{ borderBottom:`1px solid ${T.border}` }}>
            {["Workflow","Calls","Failures","Rate","Cost","Status"].map((h)=>(
              <SortableTh key={h} label={h} sortKey={colKey[h]} active={sortKey===colKey[h]} dir={sortDir} onToggle={toggle} />
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r)=>(
            <tr key={r.wf} style={{ borderBottom:`1px solid ${T.border}` }}>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{r.wf}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{r.calls.toLocaleString()}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:r.fails>0?T.warn:T.textDim }}>{r.fails}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:r.rate>0.2?T.crit:r.rate>0.05?T.warn:T.textDim }}>{(r.rate*100).toFixed(1)}%</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:12, color:T.text }}>{fmt$(r.cost)}</td>
              <td style={{ padding:"12px 8px" }}>{r.rate>0.2?<Pill color={T.crit}>degraded</Pill>:r.rate>0.05?<Pill color={T.warn}>warning</Pill>:<Pill color={T.accent}>healthy</Pill>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export default WorkflowHealth;
