import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { T, FONT_UI as FONT, FONT_MONO as MONO } from "../theme.js";
import { Card, Pill, fmt$, fmtK } from "../components/ui.jsx";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import { surfaceAllowsPage } from "../productSurface.js";
import {
  getTelemetrySummary, getCostTrend, getAssetSummary, getOpenFindings,
  getRecentTraces, getSecurityAlerts, getAttention,
} from "../overviewApi.js";

const ROLE_KEY = "oa-overview-role";
const SEV_RANK = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };
const SEV_COLOR = { critical: T.crit, high: T.crit, medium: T.warn, low: T.info, info: T.textDim };
const STATUS_META = {
  active:            { label: "Active",           color: T.accent },
  runtime_observed:  { label: "Runtime observed", color: T.info },
  has_findings:      { label: "Has findings",     color: T.warn },
  error_observed:    { label: "Errors observed",  color: T.crit },
  gateway_observed:  { label: "Gateway observed", color: T.purple },
};
const CATEGORY_COLOR = {
  security: T.crit, performance: T.warn, operations: T.info,
  dependency: T.teal, inventory: T.purple, governance: T.accent,
};

const fmtMs = (ms) => {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};
const fmtWhen = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

function SamplePill() {
  return (
    <span style={{ fontFamily: MONO, fontSize: 9, color: T.textMute, border: `1px solid ${T.border}`, borderRadius: 999, padding: "1px 8px", letterSpacing: "0.08em", textTransform: "uppercase" }}>
      sample
    </span>
  );
}

/** Panel header with optional click-through, guarded by the built surface. */
function PanelTitle({ title, sub, demo, target, targetLabel, onNavigate }) {
  const linked = target && surfaceAllowsPage(target);
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 14, gap: 10 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{title}</span>
        {demo && <SamplePill />}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        {sub && <span style={{ fontSize: 11, color: T.textMute, fontFamily: MONO }}>{sub}</span>}
        {linked && (
          <button onClick={() => onNavigate?.(target)}
            style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "4px 12px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer", letterSpacing: "0.04em", whiteSpace: "nowrap" }}>
            {targetLabel} →
          </button>
        )}
      </div>
    </div>
  );
}

function AttentionCard({ label, value, sub, tone, target, onNavigate }) {
  const linked = target && surfaceAllowsPage(target);
  return (
    <div onClick={linked ? () => onNavigate?.(target) : undefined}
      style={{
        flex: 1, minWidth: 160, background: T.panel, borderRadius: 8, padding: "18px 20px",
        border: `1px solid ${tone}44`, cursor: linked ? "pointer" : "default", transition: "border-color 0.15s",
      }}
      onMouseEnter={(e) => { if (linked) e.currentTarget.style.borderColor = tone; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = `${tone}44`; }}>
      <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10 }}>{label}</div>
      <div style={{ fontSize: 30, fontWeight: 700, color: tone, letterSpacing: "-0.03em", lineHeight: 1 }}>{value ?? "—"}</div>
      {sub && <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, marginTop: 8 }}>{sub}</div>}
    </div>
  );
}

function HBar({ label, value, max, color, right }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: T.text, marginBottom: 4 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ width: 9, height: 9, borderRadius: 2, background: color, display: "inline-block", flexShrink: 0 }} />
          {label}
        </span>
        <span style={{ fontFamily: MONO, color: T.textDim }}>{right ?? value}</span>
      </div>
      <div style={{ background: T.panelHi, borderRadius: 2, height: 5 }}>
        <div style={{ width: `${max > 0 ? Math.min(100, (value / max) * 100) : 0}%`, background: color, height: 5, borderRadius: 2, transition: "width 0.5s" }} />
      </div>
    </div>
  );
}

const emptyNote = (text) => (
  <div style={{ color: T.textMute, fontFamily: MONO, fontSize: 12, padding: "18px 0" }}>{text}</div>
);

export default function OverviewHub({ onNavigate }) {
  const bp = useBreakpoint();
  const [role, setRole] = useState(() => {
    const saved = localStorage.getItem(ROLE_KEY);
    return saved === "operator" ? "operator" : "executive";
  });
  const pickRole = (r) => { setRole(r); localStorage.setItem(ROLE_KEY, r); };

  const [attention, setAttention] = useState(null);
  const [summary, setSummary]     = useState(null);
  const [cost, setCost]           = useState(null);
  const [assets, setAssets]       = useState(null);
  const [findings, setFindings]   = useState(null);
  const [traces, setTraces]       = useState(null);
  const [alerts, setAlerts]       = useState(null);
  const [loading, setLoading]     = useState(true);

  const refreshAttention = useCallback(() => {
    getAttention().then(setAttention).catch(() => {});
  }, []);

  useEffect(() => {
    (async () => {
      const [att, s, c, a, f, t, al] = await Promise.all([
        getAttention(), getTelemetrySummary(), getCostTrend(30), getAssetSummary(),
        getOpenFindings(), getRecentTraces(20), getSecurityAlerts(),
      ]);
      setAttention(att); setSummary(s); setCost(c); setAssets(a);
      setFindings(f); setTraces(t); setAlerts(al);
      setLoading(false);
    })();
  }, []);

  // 30-second refresh cadence for the attention strip, surfaced as a visible
  // countdown instead of a sentence. The ref drives the cycle; state only renders it.
  const nextRef = useRef(30);
  const [nextIn, setNextIn] = useState(30);
  useEffect(() => {
    const id = setInterval(() => {
      nextRef.current -= 1;
      if (nextRef.current <= 0) {
        nextRef.current = 30;
        refreshAttention();
      }
      setNextIn(nextRef.current);
    }, 1000);
    return () => clearInterval(id);
  }, [refreshAttention]);

  const estate = useMemo(() => {
    const counts = {};
    (assets?.data.assets || []).forEach((a) =>
      (a.status || []).forEach((s) => { counts[s] = (counts[s] || 0) + 1; }));
    return Object.entries(STATUS_META)
      .map(([key, meta]) => ({ key, meta, count: counts[key] || 0 }))
      .filter((x) => x.count > 0);
  }, [assets]);

  const findingsByCategory = useMemo(() => {
    const counts = {};
    (findings?.data || []).forEach((f) => { counts[f.category] = (counts[f.category] || 0) + 1; });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [findings]);

  const topFindings = useMemo(() =>
    [...(findings?.data || [])]
      .sort((a, b) => (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0))
      .slice(0, 6),
  [findings]);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: T.textMute, fontFamily: MONO, fontSize: 13 }}>
      Loading overview…
    </div>
  );

  const att = attention || {};
  const trendData = (cost?.data.trends || []).map((p) => ({ date: p.date?.slice(5), cost: p.cost_usd }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, fontFamily: FONT }}>

      {/* ── Header: title + role toggle ─────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: bp.isMobile ? 20 : 24, fontWeight: 700, color: T.text, letterSpacing: "-0.025em" }}>Overview</h2>
        </div>
        <div style={{ display: "inline-flex", border: `1px solid ${T.border}`, borderRadius: 6, overflow: "hidden" }}>
          {["executive", "operator"].map((r) => (
            <button key={r} onClick={() => pickRole(r)}
              style={{
                background: role === r ? T.accent : "transparent",
                color: role === r ? "#FFFFFF" : T.textDim,
                border: "none", padding: "8px 20px", fontSize: 12, fontWeight: 600,
                fontFamily: FONT, cursor: "pointer", textTransform: "capitalize",
              }}>
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* ── Attention strip (both roles, 30s refresh) ───────────────────────── */}
      <div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase" }}>Attention</span>
          {att.demo && <SamplePill />}
          <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: MONO, color: T.textMute }}>
            next refresh · <span style={{ color: T.textDim }}>{nextIn}s</span>
          </span>
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <AttentionCard label="Agent needs owner" value={att.agentsNeedingOwner}
            sub="Observed AI assets without assigned ownership should be reviewed before production expansion."
            tone={(att.agentsNeedingOwner ?? 0) > 0 ? T.warn : T.accent}
            target="governance" onNavigate={onNavigate} />
        </div>
      </div>

      {/* ── Worst offender hero ─────────────────────────────────────────────── */}
      {att.worstOffender ? (
        <div onClick={surfaceAllowsPage("intelligence") ? () => onNavigate?.("intelligence") : undefined}
          style={{
            display: "flex", alignItems: "center", gap: 18, padding: "18px 24px",
            background: `${T.crit}0D`, border: `1px solid ${T.crit}33`, borderRadius: 10,
            cursor: surfaceAllowsPage("intelligence") ? "pointer" : "default",
          }}>
          <div style={{ fontSize: 26 }}>🔥</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 10, fontFamily: MONO, color: T.crit, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 4 }}>
              Needs attention today
            </div>
            <div style={{ fontSize: 16, fontWeight: 650, color: T.text, fontFamily: MONO }}>
              {att.worstOffender.asset_name}
            </div>
            <div style={{ fontSize: 12, color: T.textDim, fontFamily: MONO, marginTop: 4 }}>
              {att.worstOffender.highFindings} high-severity open finding{att.worstOffender.highFindings !== 1 ? "s" : ""} · {att.worstOffender.errorTraces} error trace{att.worstOffender.errorTraces !== 1 ? "s" : ""}
            </div>
          </div>
          {surfaceAllowsPage("intelligence") && (
            <span style={{ fontFamily: MONO, fontSize: 11, color: T.crit, whiteSpace: "nowrap" }}>Investigate →</span>
          )}
        </div>
      ) : (
        <div style={{ padding: "14px 24px", background: `${T.accent}0D`, border: `1px solid ${T.accent}33`, borderRadius: 10, fontSize: 13, color: T.textDim }}>
          <span style={{ color: T.accent, fontFamily: MONO }}>✓</span>&nbsp; No system needs attention right now.
        </div>
      )}

      {/* ── Executive view ──────────────────────────────────────────────────── */}
      {role === "executive" && (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {[
              { label: "Spend (period)", value: fmt$(summary?.data.total_cost_usd ?? 0), target: "cost" },
              { label: "Requests",       value: fmtK(summary?.data.total_requests ?? 0), target: "cost" },
              { label: "Tokens",         value: fmtK(summary?.data.total_tokens ?? 0), target: "cost" },
              { label: "Avg latency",    value: fmtMs(Math.round(summary?.data.avg_latency_ms ?? 0)), target: "runtime" },
            ].map((k) => (
              <div key={k.label}
                onClick={surfaceAllowsPage(k.target) ? () => onNavigate?.(k.target) : undefined}
                style={{ flex: 1, minWidth: 150, background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "18px 20px", cursor: surfaceAllowsPage(k.target) ? "pointer" : "default" }}>
                <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10, display: "flex", gap: 6, alignItems: "baseline" }}>
                  {k.label}{summary?.demo && <SamplePill />}
                </div>
                <div style={{ fontSize: 26, fontWeight: 700, color: T.text, letterSpacing: "-0.03em" }}>{k.value}</div>
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "3fr 2fr", gap: 16 }}>
            <Card>
              <PanelTitle title="Cost trend" sub="last 30 days · runtime estimate" demo={cost?.demo}
                target="cost" targetLabel="Cost Intelligence" onNavigate={onNavigate} />
              {trendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={trendData}>
                    <defs>
                      <linearGradient id="ovCost" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={T.accent} stopOpacity={0.35} />
                        <stop offset="100%" stopColor={T.accent} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={T.border} vertical={false} />
                    <XAxis dataKey="date" stroke={T.textMute} style={{ fontFamily: MONO, fontSize: 10 }} />
                    <YAxis stroke={T.textMute} style={{ fontFamily: MONO, fontSize: 10 }} tickFormatter={(v) => `$${v.toFixed(0)}`} />
                    <Tooltip contentStyle={{ background: "#FFFFFF", border: `1px solid ${T.border}`, borderRadius: 8, boxShadow: "0 4px 12px rgba(15,23,42,0.08)", fontFamily: MONO, fontSize: 11 }} formatter={(v) => [fmt$(v), "cost"]} />
                    <Area type="monotone" dataKey="cost" stroke={T.accent} strokeWidth={1.5} fill="url(#ovCost)" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : emptyNote("No cost trend data for this period.")}
            </Card>

            <Card>
              <PanelTitle title="AI estate status" sub={`${assets?.data.assets.length ?? 0} systems`} demo={assets?.demo}
                target="intelligence" targetLabel="Asset Intelligence" onNavigate={onNavigate} />
              {estate.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {estate.map(({ key, meta, count }) => (
                    <HBar key={key} label={meta.label} value={count} max={assets?.data.assets.length || 1} color={meta.color} />
                  ))}
                </div>
              ) : emptyNote("No systems discovered yet.")}
            </Card>
          </div>
        </>
      )}

      {/* ── Operator view ───────────────────────────────────────────────────── */}
      {role === "operator" && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "3fr 2fr", gap: 16 }}>
            <Card>
              <PanelTitle title="Recent executions" sub={`${traces?.data.length ?? 0} traces`} demo={traces?.demo}
                target="runtime" targetLabel="Runtime" onNavigate={onNavigate} />
              {(traces?.data || []).length > 0 ? (
                <div>
                  {traces.data.slice(0, 8).map((t, i) => (
                    <div key={t.trace_id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 0", borderBottom: i < Math.min(traces.data.length, 8) - 1 ? `1px solid ${T.border}` : "none" }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {t.root_span_name || t.trace_id.slice(0, 12)}
                        </div>
                        <div style={{ fontSize: 10, fontFamily: MONO, color: T.textMute, marginTop: 2 }}>
                          {t.service_name || "—"} · {fmtWhen(t.start_time)}
                        </div>
                      </div>
                      <span style={{ fontFamily: MONO, fontSize: 12, color: T.text, whiteSpace: "nowrap" }}>{fmtMs(t.duration_ms)}</span>
                      <span style={{ fontFamily: MONO, fontSize: 11, color: T.textDim, whiteSpace: "nowrap" }}>{t.span_count} steps</span>
                      {t.error_count > 0
                        ? <Pill color={T.crit}>{t.error_count} error{t.error_count > 1 ? "s" : ""}</Pill>
                        : <span style={{ fontFamily: MONO, fontSize: 11, color: T.textMute }}>—</span>}
                    </div>
                  ))}
                </div>
              ) : emptyNote("No executions observed yet.")}
            </Card>

            <Card>
              <PanelTitle title="Open findings by category" sub={`${findings?.data.length ?? 0} open`} demo={findings?.demo}
                target="intelligence" targetLabel="Asset Intelligence" onNavigate={onNavigate} />
              {findingsByCategory.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {findingsByCategory.map(([cat, count]) => (
                    <HBar key={cat} label={cat} value={count} max={findingsByCategory[0][1]} color={CATEGORY_COLOR[cat] || T.textDim} />
                  ))}
                </div>
              ) : emptyNote("No open findings.")}
            </Card>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "1fr 1fr", gap: 16 }}>
            <Card>
              <PanelTitle title="Top open findings" demo={findings?.demo}
                target="intelligence" targetLabel="All findings" onNavigate={onNavigate} />
              {topFindings.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {topFindings.map((f) => (
                    <div key={f.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <Pill color={SEV_COLOR[f.severity] || T.textDim}>{f.severity}</Pill>
                      <span style={{ flex: 1, minWidth: 0, fontSize: 13, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {f.title}
                        {(f.occurrence_count || 1) > 1 && (
                          <span style={{ marginLeft: 8, fontFamily: MONO, fontSize: 10, color: T.textDim }}>×{f.occurrence_count}</span>
                        )}
                      </span>
                      <span style={{ fontFamily: MONO, fontSize: 10, color: T.textMute, whiteSpace: "nowrap" }}>{f.category}</span>
                    </div>
                  ))}
                </div>
              ) : emptyNote("No open findings.")}
            </Card>

            <Card>
              <PanelTitle title="Detection rules firing" sub={`${alerts?.data.length ?? 0} alert${(alerts?.data.length ?? 0) !== 1 ? "s" : ""}`} demo={alerts?.demo}
                target="security_intel" targetLabel="Security" onNavigate={onNavigate} />
              {(alerts?.data || []).length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {alerts.data.slice(0, 6).map((a, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                      <Pill color={a.sev === "critical" ? T.crit : a.sev === "warning" ? T.warn : T.info}>{a.sev}</Pill>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, color: T.text, fontFamily: MONO }}>{a.type} · {a.entity}</div>
                        <div style={{ fontSize: 11, color: T.textMute, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.msg}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : emptyNote("No detection rules firing.")}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
