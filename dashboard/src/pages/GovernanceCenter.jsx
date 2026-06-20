import React, { useState, useEffect, useMemo, useCallback } from "react";
import { fetchAgents, claimInventoryAgent } from "../api.js";

const T = {
  bg: "#0A0B0F", panel: "#0F1117", panelHi: "#141823",
  border: "#1E2230", borderHi: "#2A3242",
  text: "#E8ECF4", textDim: "#7A8499", textMute: "#4B5468",
  accent: "#7CFFB2", warn: "#FFB547", crit: "#FF5C7A",
  info: "#6FA8FF", yellow: "#FFD700", purple: "#B47AFF",
};
const MONO = "'JetBrains Mono','IBM Plex Mono',monospace";
const FONT = "'Geist','Söhne',-apple-system,sans-serif";

function relativeTime(iso) {
  if (!iso) return "—";
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (d === 0) return "today";
  if (d === 1) return "yesterday";
  return `${d}d ago`;
}

function CoverageBar({ label, value, total, color = T.accent, target }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: T.text, marginBottom: 6 }}>
        <span>{label}</span>
        <span style={{ fontFamily: MONO }}>
          <span style={{ color }}>{value}</span>
          <span style={{ color: T.textMute }}>/{total} ({pct}%)</span>
          {target && <span style={{ color: pct >= target ? T.accent : T.warn, marginLeft: 8, fontSize: 11 }}>{pct >= target ? "✓" : `${target}% target`}</span>}
        </span>
      </div>
      <div style={{ background: T.panelHi, borderRadius: 2, height: 6, position: "relative" }}>
        <div style={{ width: `${pct}%`, background: color, height: 6, borderRadius: 2, transition: "width 0.5s" }} />
        {target && <div style={{ position: "absolute", top: -1, left: `${target}%`, width: 1, height: 8, background: T.textMute, opacity: 0.4 }} />}
      </div>
    </div>
  );
}

function ClaimModal({ agent, onClose, onSave }) {
  const [owner, setOwner]   = useState("");
  const [team, setTeam]     = useState(agent?.team || "");
  const [saving, setSaving] = useState(false);
  const [err, setErr]       = useState("");

  const submit = async () => {
    if (!owner.trim()) { setErr("Owner is required"); return; }
    setSaving(true);
    try { await onSave(agent.agent_id, { owner_name: owner, team }); onClose(); }
    catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "#000A", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: 28, minWidth: 360, fontFamily: FONT }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: T.text, marginBottom: 6 }}>Assign Owner</div>
        <div style={{ fontSize: 13, color: T.textDim, marginBottom: 20 }}>
          Claiming <strong style={{ color: T.text, fontFamily: MONO }}>{agent?.agent_name}</strong>
        </div>
        {[
          { label: "Owner", value: owner, set: setOwner, placeholder: "Email or display name" },
          { label: "Team",  value: team,  set: setTeam,  placeholder: "Team name" },
        ].map(({ label, value, set, placeholder }) => (
          <div key={label} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, color: T.textMute, fontFamily: MONO, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
            <input value={value} onChange={e => set(e.target.value)} placeholder={placeholder}
              style={{ width: "100%", background: T.panelHi, border: `1px solid ${T.border}`, color: T.text, padding: "8px 12px", borderRadius: 4, fontSize: 13, fontFamily: FONT }} />
          </div>
        ))}
        {err && <div style={{ color: T.crit, fontSize: 12, fontFamily: MONO, marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 20 }}>
          <button onClick={onClose} style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "8px 16px", borderRadius: 4, fontSize: 13, cursor: "pointer" }}>Cancel</button>
          <button onClick={submit} disabled={saving} style={{ background: T.accent, color: T.bg, border: "none", padding: "8px 16px", borderRadius: 4, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            {saving ? "Assigning…" : "Assign"}
          </button>
        </div>
      </div>
    </div>
  );
}

const TH = ({ children }) => (
  <th style={{ textAlign: "left", padding: "8px 14px", fontSize: 10, fontFamily: MONO, color: T.textMute, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 500, borderBottom: `1px solid ${T.border}`, background: T.panelHi }}>
    {children}
  </th>
);
const TD = ({ children, style }) => (
  <td style={{ padding: "10px 14px", fontSize: 13, color: T.text, borderBottom: `1px solid ${T.border}`, verticalAlign: "middle", ...style }}>
    {children}
  </td>
);

export default function GovernanceCenter() {
  const [agents, setAgents]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [tab, setTab]           = useState("approvals");
  const [claimTarget, setClaimTarget] = useState(null);
  const [toastMsg, setToastMsg] = useState("");

  const toast = (msg) => { setToastMsg(msg); setTimeout(() => setToastMsg(""), 3000); };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const raw = await fetchAgents({ limit: 500 });
      setAgents(Array.isArray(raw) ? raw : raw?.agents || raw?.items || []);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const total            = agents.length;
  const managed          = useMemo(() => agents.filter(a => a.lifecycle_status === "managed"), [agents]);
  const unassigned       = useMemo(() => agents.filter(a => a.lifecycle_status === "unassigned"), [agents]);
  const needsValidation  = useMemo(() => agents.filter(a => a.lifecycle_status === "needs_validation"), [agents]);
  const retired          = useMemo(() => agents.filter(a => a.lifecycle_status === "retired"), [agents]);

  const withEnv          = agents.filter(a => a.environment && a.environment !== "unknown").length;
  const withCrit         = agents.filter(a => a.criticality && a.criticality !== "unknown").length;
  const withOwner        = agents.filter(a => a.owner && a.owner !== "Unassigned").length;
  const withPurpose      = agents.filter(a => a.business_purpose || a.description).length;

  const pendingApprovals = [...needsValidation, ...unassigned];
  const ownershipGap     = Math.max(0, Math.ceil(total * 0.9) - withOwner);

  const handleClaim = async (agentId, body) => {
    await claimInventoryAgent(agentId, body);
    toast("Owner assigned successfully");
    await load();
  };

  const tabs = [
    { id: "approvals", label: `Approvals (${pendingApprovals.length})` },
    { id: "ownership", label: `Ownership (${Math.round(withOwner / Math.max(1, total) * 100)}% covered)` },
    { id: "policy",    label: "Policy Coverage" },
  ];

  return (
    <div style={{ fontFamily: FONT }}>
      {toastMsg && (
        <div style={{ position: "fixed", bottom: 24, right: 24, background: T.panelHi, border: `1px solid ${T.accent}`, color: T.accent, padding: "10px 18px", borderRadius: 6, fontFamily: MONO, fontSize: 13, zIndex: 2000 }}>
          {toastMsg}
        </div>
      )}
      {claimTarget && <ClaimModal agent={claimTarget} onClose={() => setClaimTarget(null)} onSave={handleClaim} />}

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 0, background: T.panelHi, border: `1px solid ${T.border}`, borderRadius: 6, padding: 3, marginBottom: 24, alignSelf: "flex-start", width: "fit-content" }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ background: tab === t.id ? T.panel : "transparent", border: tab === t.id ? `1px solid ${T.border}` : "1px solid transparent", color: tab === t.id ? T.text : T.textDim, padding: "7px 18px", borderRadius: 4, fontSize: 12, fontFamily: MONO, cursor: "pointer", transition: "all 0.12s" }}>
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ color: T.textMute, fontFamily: MONO, fontSize: 13, padding: "32px 0", textAlign: "center" }}>Loading agents…</div>
      ) : tab === "approvals" ? (

        /* ── Approvals ─────────────────────────────────────────────────────── */
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
            {[
              { label: "Pending Validation", count: needsValidation.length, color: T.warn,   desc: "Potential agents requiring confirmation" },
              { label: "Pending Ownership",  count: unassigned.length,      color: T.yellow, desc: "Verified agents without an assigned owner" },
            ].map(({ label, count, color, desc }) => (
              <div key={label} style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "20px 24px" }}>
                <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10 }}>{label}</div>
                <div style={{ fontSize: 36, fontWeight: 700, color, letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 8 }}>{count}</div>
                <div style={{ fontSize: 12, color: T.textMute }}>{desc}</div>
              </div>
            ))}
          </div>

          {pendingApprovals.length === 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "28px", background: T.panel, border: `1px solid ${T.accent}33`, borderRadius: 8, color: T.accent, fontFamily: MONO, fontSize: 14 }}>
              <span style={{ fontSize: 22 }}>✓</span> All agents are validated and assigned. Governance is up to date.
            </div>
          ) : (
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <TH>Agent</TH>
                    <TH>Action Required</TH>
                    <TH>Team</TH>
                    <TH>First Seen</TH>
                    <TH>Actions</TH>
                  </tr>
                </thead>
                <tbody>
                  {pendingApprovals.map(agent => {
                    const isPending = agent.lifecycle_status === "needs_validation";
                    return (
                      <tr key={agent.agent_id || agent.id}>
                        <TD>
                          <div style={{ fontFamily: MONO, fontSize: 13, color: T.text }}>{agent.agent_name || agent.agent_id_raw}</div>
                          <div style={{ fontSize: 11, color: T.textMute, marginTop: 2 }}>{agent.agent_id}</div>
                        </TD>
                        <TD>
                          <span style={{ display: "inline-block", background: isPending ? T.warn + "1A" : T.yellow + "1A", color: isPending ? T.warn : T.yellow, border: `1px solid ${isPending ? T.warn : T.yellow}33`, fontSize: 11, fontFamily: MONO, padding: "2px 9px", borderRadius: 4 }}>
                            {isPending ? "Validate Agent" : "Assign Owner"}
                          </span>
                        </TD>
                        <TD><span style={{ color: T.textDim }}>{agent.team || "—"}</span></TD>
                        <TD><span style={{ fontFamily: MONO, color: T.textDim, fontSize: 12 }}>{relativeTime(agent.first_seen_at || agent.created_at)}</span></TD>
                        <TD>
                          {!isPending && (
                            <button onClick={() => setClaimTarget(agent)} style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "4px 12px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer" }}>
                              Assign Owner
                            </button>
                          )}
                        </TD>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

      ) : tab === "ownership" ? (

        /* ── Ownership ─────────────────────────────────────────────────────── */
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {[
              { label: "Owned",    count: withOwner,         color: T.accent },
              { label: "Unowned",  count: total - withOwner, color: T.yellow },
              { label: "Coverage", count: `${total > 0 ? Math.round(withOwner / total * 100) : 0}%`, color: T.info },
              { label: "Gap to 90%", count: ownershipGap,   color: ownershipGap > 0 ? T.warn : T.accent },
            ].map(({ label, count, color }) => (
              <div key={label} style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "18px 20px" }}>
                <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10 }}>{label}</div>
                <div style={{ fontSize: 30, fontWeight: 700, color, letterSpacing: "-0.03em" }}>{count}</div>
              </div>
            ))}
          </div>

          <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "20px 24px" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 16 }}>Ownership Coverage</div>
            <div style={{ marginBottom: 10, background: T.panelHi, borderRadius: 2, height: 8, position: "relative" }}>
              <div style={{ width: `${total > 0 ? (withOwner / total) * 100 : 0}%`, background: T.accent, height: 8, borderRadius: 2 }} />
              <div style={{ position: "absolute", top: -2, left: "90%", width: 2, height: 12, background: T.textMute, opacity: 0.5 }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontFamily: MONO, color: T.textMute, marginTop: 6 }}>
              <span><span style={{ color: T.accent }}>{withOwner}</span> owned</span>
              <span>90% target</span>
              <span><span style={{ color: T.yellow }}>{total - withOwner}</span> unassigned</span>
            </div>
          </div>

          {unassigned.length > 0 && (
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
              <div style={{ padding: "16px 20px", borderBottom: `1px solid ${T.border}`, fontSize: 14, fontWeight: 600, color: T.text }}>
                Unassigned Agents ({unassigned.length})
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <TH>Agent</TH>
                    <TH>Team</TH>
                    <TH>Environment</TH>
                    <TH>First Seen</TH>
                    <TH>Assign</TH>
                  </tr>
                </thead>
                <tbody>
                  {unassigned.map(agent => (
                    <tr key={agent.agent_id || agent.id}>
                      <TD><span style={{ fontFamily: MONO, color: T.yellow }}>{agent.agent_name || agent.agent_id_raw}</span></TD>
                      <TD><span style={{ color: T.textDim }}>{agent.team || "—"}</span></TD>
                      <TD><span style={{ color: T.textDim, fontSize: 12, fontFamily: MONO }}>{agent.environment || "—"}</span></TD>
                      <TD><span style={{ fontFamily: MONO, color: T.textDim, fontSize: 12 }}>{relativeTime(agent.first_seen_at || agent.created_at)}</span></TD>
                      <TD>
                        <button onClick={() => setClaimTarget(agent)} style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "4px 12px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer" }}>
                          Assign Owner
                        </button>
                      </TD>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      ) : (

        /* ── Policy Coverage ───────────────────────────────────────────────── */
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "24px 28px" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 20 }}>Classification Completeness</div>
            <CoverageBar label="Owner Assigned"            value={withOwner}  total={total} color={T.accent}  target={90} />
            <CoverageBar label="Environment Classified"    value={withEnv}    total={total} color={T.info}    target={95} />
            <CoverageBar label="Criticality Assessed"      value={withCrit}   total={total} color={T.warn}    target={85} />
            <CoverageBar label="Business Purpose Documented" value={withPurpose} total={total} color={T.purple} target={70} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {[
              { label: "Managed",        count: managed.length,  color: T.accent,  sub: "Fully governed" },
              { label: "Needs Attention", count: needsValidation.length + unassigned.length, color: T.warn, sub: "Action required" },
              { label: "Retired",        count: retired.length,  color: "#555",    sub: "Decommissioned" },
            ].map(({ label, count, color, sub }) => (
              <div key={label} style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "18px 20px" }}>
                <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10 }}>{label}</div>
                <div style={{ fontSize: 28, fontWeight: 700, color, letterSpacing: "-0.03em", lineHeight: 1 }}>{count}</div>
                <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, marginTop: 6 }}>{sub}</div>
              </div>
            ))}
          </div>

          <div style={{ padding: "14px 18px", background: T.info + "0D", border: `1px solid ${T.info}33`, borderRadius: 6, fontSize: 12, color: T.textDim }}>
            <span style={{ color: T.info }}>ℹ</span>&nbsp; Policy coverage improves as agents are claimed, classified by environment and criticality, and have their business purpose documented.
          </div>
        </div>
      )}
    </div>
  );
}
