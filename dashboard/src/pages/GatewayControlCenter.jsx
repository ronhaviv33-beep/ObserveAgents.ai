import { useState, useEffect, useMemo, useCallback } from "react";
import { fetchIntelligenceFindings, fetchIntelligenceAssetSummary, dismissFinding, reopenFinding } from "../api.js";

/**
 * Gateway Control Center (GCR3) — the action workspace.
 *
 * Shows only the agents whose runtime evidence recommends Gateway-level
 * review (candidates = findings with category="control"), with the evidence
 * that put them there and the controls that would address it.
 *
 * Observe-only: nothing here blocks or reroutes. Everyone can view;
 * only admins act (dismiss / reopen) — enforced server-side too.
 */

const T = {
  bg: "#070A14", panel: "#0D1322", panelHi: "#141C31",
  border: "#1D2740", borderHi: "#31406B",
  text: "#E9EEF9", textDim: "#9AA9CB", textMute: "#5E6D90",
  accent: "#3DDC97", warn: "#F5C544", crit: "#FF4D6D",
  info: "#2DD4BF", purple: "#A78BFA",
};
const MONO = "'JetBrains Mono','IBM Plex Mono',monospace";
const FONT = "'Geist','Söhne',-apple-system,sans-serif";

const SEV = {
  high:   { color: T.crit, label: "High" },
  medium: { color: T.warn, label: "Medium" },
  low:    { color: T.info, label: "Low" },
};

const KIND_META = {
  hard:    { label: "requires Gateway routing", color: T.crit },
  routing: { label: "routing step",             color: T.purple },
  soft:    { label: "available now",            color: T.accent },
};

function relativeTime(ts) {
  if (!ts) return "—";
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000), h = Math.floor(diff / 3600000), d = Math.floor(diff / 86400000);
  if (m < 2) return "just now";
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  return `${d}d ago`;
}

function Pill({ children, color = T.textDim }) {
  return (
    <span style={{ display: "inline-block", background: color + "1A", color, border: `1px solid ${color}44`,
      fontSize: 10, fontFamily: MONO, padding: "2px 8px", borderRadius: 4, whiteSpace: "nowrap" }}>
      {children}
    </span>
  );
}

function ActionBtn({ onClick, children, danger }) {
  return (
    <button onClick={onClick} style={{ background: "transparent", color: danger ? T.crit : T.textDim,
      border: `1px solid ${danger ? T.crit + "55" : T.border}`, borderRadius: 6, padding: "4px 12px",
      fontSize: 11, fontFamily: MONO, cursor: "pointer" }}>
      {children}
    </button>
  );
}

function ControlsList({ controls }) {
  if (!controls?.length) return <span style={{ color: T.textMute }}>—</span>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {controls.map((c) => {
        const meta = KIND_META[c.kind] || KIND_META.soft;
        return (
          <div key={c.control} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, color: T.text }}>{c.control}</span>
            <Pill color={meta.color}>{meta.label}</Pill>
          </div>
        );
      })}
    </div>
  );
}

function CandidateRow({ cand, asset, isAdmin, expanded, onToggle, onAction }) {
  const sev = SEV[cand.severity] || SEV.medium;
  const ev = cand.evidence || {};
  const name = asset?.asset_name || asset?.service_name || cand.asset_key.slice(0, 12) + "…";
  const owner = asset?.owner || asset?.team || null;
  const hasHard = (ev.recommended_controls || []).some((c) => c.kind === "hard");
  return (
    <div style={{ border: `1px solid ${expanded ? T.borderHi : T.border}`, borderRadius: 10, background: T.panel, overflow: "hidden" }}>
      <div onClick={onToggle} style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px", cursor: "pointer", flexWrap: "wrap" }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: sev.color, flexShrink: 0 }} />
        <div style={{ minWidth: 160, flex: "1 1 160px" }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: T.text }}>{name}</div>
          <div style={{ fontSize: 11, fontFamily: MONO, color: T.textMute }}>
            {ev.environment || "unknown"}{owner ? ` · ${owner}` : " · no owner"}
          </div>
        </div>
        <Pill color={sev.color}>{sev.label} risk</Pill>
        <Pill>{ev.trigger_count || 0} finding{(ev.trigger_count || 0) !== 1 ? "s" : ""}</Pill>
        {hasHard && cand.status === "open" && <Pill color={T.purple}>routing required</Pill>}
        <span style={{ fontSize: 11, fontFamily: MONO, color: T.textMute, marginLeft: "auto" }}>{relativeTime(cand.last_seen)}</span>
        <span style={{ color: T.textMute, fontSize: 12 }}>{expanded ? "▾" : "▸"}</span>
      </div>
      {expanded && (
        <div style={{ borderTop: `1px solid ${T.border}`, padding: "16px 18px", background: T.panelHi, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20 }}>
          <div>
            <div style={{ fontSize: 10, fontFamily: MONO, color: T.textMute, letterSpacing: "0.08em", marginBottom: 8 }}>WHY THIS AGENT IS HERE</div>
            <div style={{ fontSize: 12, color: T.textDim, lineHeight: 1.6, marginBottom: 10 }}>{ev.reason || cand.summary}</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {(ev.trigger_finding_types || []).map((t) => <Pill key={t} color={T.warn}>{t}</Pill>)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10, fontFamily: MONO, color: T.textMute, letterSpacing: "0.08em", marginBottom: 8 }}>SUGGESTED CONTROLS</div>
            <ControlsList controls={ev.recommended_controls} />
            <div style={{ fontSize: 11, color: T.textMute, marginTop: 12, lineHeight: 1.5 }}>
              Hard controls only work after this agent's traffic is routed through the Gateway.
              Nothing is applied automatically.
            </div>
            {isAdmin && (
              <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
                {cand.status === "open"
                  ? <ActionBtn danger onClick={(e) => { e.stopPropagation(); onAction("dismiss", cand.id); }}>Dismiss recommendation</ActionBtn>
                  : <ActionBtn onClick={(e) => { e.stopPropagation(); onAction("reopen", cand.id); }}>Reopen</ActionBtn>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function GatewayControlCenter({ isAdmin = false, focusAssetKey = null, onClearFocus }) {
  const [candidates, setCandidates] = useState(null);
  const [assets, setAssets] = useState({});
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    try {
      const [finds, summary] = await Promise.all([
        fetchIntelligenceFindings({ category: "control" }),
        fetchIntelligenceAssetSummary(),
      ]);
      const byKey = {};
      for (const a of summary?.assets || []) byKey[a.asset_key] = a;
      setCandidates(finds);
      setAssets(byKey);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { (async () => { await load(); })(); }, [load]);

  const act = useCallback(async (action, id) => {
    try {
      await (action === "dismiss" ? dismissFinding(id) : reopenFinding(id));
      await load();
    } catch (e) {
      setError(e.message);
    }
  }, [load]);

  const filtered = useMemo(() => {
    if (!candidates) return null;
    return focusAssetKey ? candidates.filter((c) => c.asset_key === focusAssetKey) : candidates;
  }, [candidates, focusAssetKey]);

  const open = useMemo(() =>
    (filtered || [])
      .filter((c) => c.status === "open")
      .sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "high" ? -1 : 1)),
  [filtered]);
  const closed = useMemo(() => (filtered || []).filter((c) => c.status !== "open"), [filtered]);
  const highCount = open.filter((c) => c.severity === "high").length;

  if (error) return <div style={{ color: T.crit, fontFamily: MONO, fontSize: 13, padding: 24 }}>{error}</div>;
  if (filtered === null) return <div style={{ color: T.textDim, fontFamily: MONO, fontSize: 13, padding: 24 }}>Loading control candidates…</div>;

  return (
    <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 24, maxWidth: 1100 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <div style={{ fontSize: 13, color: T.textDim, lineHeight: 1.6, flex: "1 1 420px" }}>
          Agents whose runtime evidence recommends Gateway-level review — with the findings that put
          them here and the controls that would address them.{" "}
          <span style={{ color: T.accent }}>Observe first. Control only what matters.</span>{" "}
          Nothing on this page blocks or reroutes traffic.
        </div>
        <div style={{ display: "flex", gap: 18, fontFamily: MONO, fontSize: 12 }}>
          <span style={{ color: T.text }}>{open.length} <span style={{ color: T.textMute }}>recommended</span></span>
          <span style={{ color: T.crit }}>{highCount} <span style={{ color: T.textMute }}>high risk</span></span>
          <span style={{ color: T.textDim }}>{closed.length} <span style={{ color: T.textMute }}>dismissed/resolved</span></span>
        </div>
      </div>

      {focusAssetKey && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Pill color={T.info}>filtered to one agent</Pill>
          <button onClick={onClearFocus} style={{ background: "transparent", border: "none", color: T.textDim, fontSize: 11, fontFamily: MONO, cursor: "pointer", textDecoration: "underline" }}>
            show all candidates
          </button>
        </div>
      )}

      <div>
        <div style={{ fontSize: 11, fontFamily: MONO, color: T.textMute, letterSpacing: "0.1em", marginBottom: 10 }}>RECOMMENDED FOR CONTROL</div>
        {open.length === 0 ? (
          <div style={{ border: `1px dashed ${T.border}`, borderRadius: 10, padding: "28px 24px", color: T.textDim, fontSize: 13, lineHeight: 1.6 }}>
            No agents are currently recommended for Gateway control.
            Candidates appear automatically when runtime evidence shows high-risk behavior —
            MCP tools in production, unknown providers, database reach, repeated failures, or
            combinations that warrant human review.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {open.map((c) => (
              <CandidateRow key={c.id} cand={c} asset={assets[c.asset_key]} isAdmin={isAdmin}
                expanded={expanded === c.id} onToggle={() => setExpanded(expanded === c.id ? null : c.id)}
                onAction={act} />
            ))}
          </div>
        )}
      </div>

      {closed.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontFamily: MONO, color: T.textMute, letterSpacing: "0.1em", marginBottom: 10 }}>DISMISSED / RESOLVED</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, opacity: 0.65 }}>
            {closed.map((c) => (
              <CandidateRow key={c.id} cand={c} asset={assets[c.asset_key]} isAdmin={isAdmin}
                expanded={expanded === c.id} onToggle={() => setExpanded(expanded === c.id ? null : c.id)}
                onAction={act} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
