import { useState, useCallback, useEffect } from "react";
import { authFetch, BASE } from "../api.js";
import { T, FONT_MONO } from "../theme.js";
import { Pill } from "./ui.jsx";

// Model Policy Rules and the Audit Log table were removed from this page.
// The backend keeps GET /audit (read-only over telemetry, dormant while
// nothing calls it) and the /policies enforcement pipeline untouched.

export default function SecurityPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [alertsOpen, setAlertsOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const a = await authFetch(`${BASE}/security/alerts`).then((x) => x.json());
      setAlerts(a);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { (async () => { await load(); })(); }, [load]);

  const alertColor = (s) => s==="critical"?T.crit:s==="warning"?T.warn:T.info;

  if (loading) return <div style={{ color:T.textDim, fontFamily:FONT_MONO, padding:24 }}>Loading security data…</div>;

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:14 }}>

      {/* KPI strip */}
      {(() => {
        const kpis = [
          { label:"Live Alerts",     value:alerts.length,                                color:alerts.length>0?T.crit:T.accent },
          { label:"Critical Alerts", value:alerts.filter(a=>a.sev==="critical").length,  color:T.crit },
          { label:"Warning Alerts",  value:alerts.filter(a=>a.sev==="warning").length,   color:T.warn },
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
          Monitor runtime security alerts derived from real telemetry across your AI operations.
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(180px, 1fr))", gap:12 }}>
          {[
            { label:"Live Alerts",     value:alerts.length,                                color:alerts.length>0?T.crit:T.accent, note:"Active findings" },
            { label:"Critical Alerts", value:alerts.filter(a=>a.sev==="critical").length,  color:T.crit,                          note:"Require immediate review" },
            { label:"Warning Alerts",  value:alerts.filter(a=>a.sev==="warning").length,   color:T.warn,                          note:"Monitor closely" },
          ].map(({ label, value, color, note }) => (
            <div key={label} style={{ background:T.panelHi, border:`1px solid ${T.border}`, borderRadius:6, padding:"14px 16px" }}>
              <div style={{ fontSize:9, fontFamily:FONT_MONO, color:T.textMute, letterSpacing:"0.12em", textTransform:"uppercase", marginBottom:8 }}>{label}</div>
              <div style={{ fontSize:26, fontWeight:700, color, letterSpacing:"-0.02em", lineHeight:1 }}>{value}</div>
              <div style={{ fontSize:10, color:T.textMute, fontFamily:FONT_MONO, marginTop:6 }}>{note}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
