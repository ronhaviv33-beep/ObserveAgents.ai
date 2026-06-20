import React, { useState, useEffect, useMemo, useCallback } from "react";
import { fetchAgents, claimInventoryAgent, validateInventoryAgent, rejectInventoryAgent } from "../api.js";

const T = {
  bg: "#0A0B0F", panel: "#0F1117", panelHi: "#141823",
  border: "#1E2230", borderHi: "#2A3142",
  text: "#E8ECF4", textDim: "#7A8499", textMute: "#4B5468",
  accent: "#7CFFB2", warn: "#FFB547", crit: "#FF5C7A",
  info: "#6FA8FF", yellow: "#FFD700", purple: "#B47AFF",
};
const MONO = "'JetBrains Mono','IBM Plex Mono',monospace";
const FONT = "'Geist','Söhne',-apple-system,sans-serif";

function relativeTime(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000), h = Math.floor(diff / 3600000), d = Math.floor(diff / 86400000);
  if (m < 2) return "just now";
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
const fmtUSD = (v) => v > 0 ? "$" + (+(v)).toFixed(2) : "—";

const SOURCE_MAP = {
  gateway_telemetry: { label: "Gateway",    color: T.accent },
  github:            { label: "GitHub",     color: T.info },
  n8n:               { label: "n8n",        color: T.purple },
  slack:             { label: "Slack",      color: "#E8A138" },
  jira:              { label: "Jira",       color: T.warn },
  servicenow:        { label: "ServiceNow", color: T.crit },
  mcp:               { label: "MCP",        color: T.purple },
};

function SourceBadge({ source }) {
  const m = SOURCE_MAP[source] || { label: source || "Unknown", color: T.textDim };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: m.color + "1A", color: m.color, border: `1px solid ${m.color}33`, fontSize: 10, fontFamily: MONO, padding: "2px 8px", borderRadius: 20, letterSpacing: "0.05em" }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: m.color }} />
      {m.label}
    </span>
  );
}

function ConfidenceBadge({ score }) {
  const color = score >= 80 ? T.accent : score >= 50 ? T.warn : T.crit;
  return (
    <span style={{ fontFamily: MONO, fontSize: 12, color }}>
      {score ?? "—"}%
    </span>
  );
}

function LifecycleBadge({ status }) {
  const map = {
    unassigned:       { label: "Unassigned",      color: T.yellow },
    needs_validation: { label: "Needs Validation", color: T.warn },
    managed:          { label: "Managed",          color: T.accent },
    retired:          { label: "Retired",          color: "#555" },
  };
  const m = map[status] || { label: status || "—", color: T.textDim };
  return (
    <span style={{ display: "inline-block", background: m.color + "1A", color: m.color, border: `1px solid ${m.color}33`, fontSize: 10, fontFamily: MONO, padding: "2px 8px", borderRadius: 4, letterSpacing: "0.05em" }}>
      {m.label}
    </span>
  );
}

function ActionBtn({ label, color, onClick }) {
  const [hover, setHover] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ background: hover ? color + "22" : "transparent", border: `1px solid ${hover ? color : T.border}`, color: hover ? color : T.textDim, padding: "4px 10px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer", transition: "all 0.12s" }}
    >
      {label}
    </button>
  );
}

function ClaimModal({ agent, onClose, onSave }) {
  const [owner, setOwner] = useState("");
  const [team, setTeam]   = useState(agent?.team || "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!owner.trim()) { setErr("Owner is required"); return; }
    setSaving(true);
    try {
      await onSave(agent.agent_id, { owner_name: owner, team, agent_name: agent.agent_name });
      onClose();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "#000A", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: 28, minWidth: 360, fontFamily: FONT }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: T.text, marginBottom: 18 }}>Claim Agent</div>
        <div style={{ fontSize: 13, color: T.textDim, marginBottom: 20 }}>Assign ownership to <strong style={{ color: T.text, fontFamily: MONO }}>{agent?.agent_name}</strong></div>
        {[
          { label: "Owner", value: owner, set: setOwner, placeholder: "Email or name" },
          { label: "Team",  value: team,  set: setTeam,  placeholder: "Team name" },
        ].map(({ label, value, set, placeholder }) => (
          <div key={label} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
            <input value={value} onChange={e => set(e.target.value)} placeholder={placeholder}
              style={{ width: "100%", background: T.panelHi, border: `1px solid ${T.border}`, color: T.text, padding: "8px 12px", borderRadius: 4, fontSize: 13, fontFamily: FONT }} />
          </div>
        ))}
        {err && <div style={{ color: T.crit, fontSize: 12, fontFamily: MONO, marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 20 }}>
          <button onClick={onClose} style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "8px 16px", borderRadius: 4, fontSize: 13, cursor: "pointer" }}>Cancel</button>
          <button onClick={submit} disabled={saving} style={{ background: T.accent, color: T.bg, border: "none", padding: "8px 16px", borderRadius: 4, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            {saving ? "Claiming…" : "Claim"}
          </button>
        </div>
      </div>
    </div>
  );
}

function EvidenceDrawer({ agent, onClose }) {
  if (!agent) return null;
  const evidence = typeof agent.evidence === "string" ? JSON.parse(agent.evidence || "{}") : (agent.evidence || {});
  return (
    <div style={{ position: "fixed", inset: 0, background: "#000A", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: 28, minWidth: 420, maxWidth: 560, fontFamily: FONT }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: T.text, marginBottom: 6 }}>Discovery Evidence</div>
        <div style={{ fontSize: 13, color: T.textDim, marginBottom: 20, fontFamily: MONO }}>{agent.agent_name}</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <div style={{ fontSize: 10, color: T.textMute, fontFamily: MONO, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>Discovery Source</div>
            <SourceBadge source={agent.discovery_source} />
          </div>
          <div>
            <div style={{ fontSize: 10, color: T.textMute, fontFamily: MONO, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>Confidence Score</div>
            <ConfidenceBadge score={agent.confidence_score} />
          </div>
          {Object.keys(evidence).length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: T.textMute, fontFamily: MONO, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>Evidence Signals</div>
              <pre style={{ background: T.panelHi, border: `1px solid ${T.border}`, borderRadius: 4, padding: "12px 14px", fontSize: 11, fontFamily: MONO, color: T.text, margin: 0, overflowX: "auto" }}>
                {JSON.stringify(evidence, null, 2)}
              </pre>
            </div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
          <button onClick={onClose} style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "8px 16px", borderRadius: 4, fontSize: 13, cursor: "pointer" }}>Close</button>
        </div>
      </div>
    </div>
  );
}

const TH = ({ children, style }) => (
  <th style={{ textAlign: "left", padding: "8px 12px", fontSize: 10, fontFamily: MONO, color: T.textMute, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 500, borderBottom: `1px solid ${T.border}`, background: T.panelHi, ...style }}>
    {children}
  </th>
);

const TD = ({ children, style }) => (
  <td style={{ padding: "10px 12px", fontSize: 13, color: T.text, borderBottom: `1px solid ${T.border}`, verticalAlign: "middle", ...style }}>
    {children}
  </td>
);

export default function DiscoveryCenter() {
  const [agents, setAgents]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [tab, setTab]             = useState("verified");
  const [search, setSearch]       = useState("");
  const [claimAgent, setClaimAgent] = useState(null);
  const [evidenceAgent, setEvidenceAgent] = useState(null);
  const [busy, setBusy]           = useState({});
  const [toastMsg, setToastMsg]   = useState("");

  const toast = (msg) => { setToastMsg(msg); setTimeout(() => setToastMsg(""), 3000); };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const raw = await fetchAgents({ limit: 500 });
      setAgents(Array.isArray(raw) ? raw : raw?.agents || raw?.items || []);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const verified  = useMemo(() => agents.filter(a => a.discovery_status === "verified"), [agents]);
  const potential = useMemo(() => agents.filter(a => a.discovery_status !== "verified"), [agents]);

  const filtered = useMemo(() => {
    const list = tab === "verified" ? verified : potential;
    const q = search.toLowerCase();
    return q ? list.filter(a => (a.agent_name || "").toLowerCase().includes(q) || (a.team || "").toLowerCase().includes(q) || (a.discovery_source || "").toLowerCase().includes(q)) : list;
  }, [tab, verified, potential, search]);

  const handleClaim = async (agentId, body) => {
    await claimInventoryAgent(agentId, body);
    toast("Agent claimed successfully");
    await load();
  };

  const handleValidate = async (agentId) => {
    setBusy(b => ({ ...b, [agentId]: "validate" }));
    try { await validateInventoryAgent(agentId, { validated: true }); toast("Agent validated"); await load(); }
    catch (e) { toast("Error: " + e.message); }
    finally { setBusy(b => { const n = { ...b }; delete n[agentId]; return n; }); }
  };

  const handleReject = async (agentId) => {
    setBusy(b => ({ ...b, [agentId]: "reject" }));
    try { await rejectInventoryAgent(agentId, "Rejected from Discovery Center"); toast("Agent rejected"); await load(); }
    catch (e) { toast("Error: " + e.message); }
    finally { setBusy(b => { const n = { ...b }; delete n[agentId]; return n; }); }
  };

  return (
    <div style={{ fontFamily: FONT }}>
      {toastMsg && (
        <div style={{ position: "fixed", bottom: 24, right: 24, background: T.panelHi, border: `1px solid ${T.accent}`, color: T.accent, padding: "10px 18px", borderRadius: 6, fontFamily: MONO, fontSize: 13, zIndex: 2000 }}>
          {toastMsg}
        </div>
      )}
      {claimAgent && <ClaimModal agent={claimAgent} onClose={() => setClaimAgent(null)} onSave={handleClaim} />}
      {evidenceAgent && <EvidenceDrawer agent={evidenceAgent} onClose={() => setEvidenceAgent(null)} />}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div style={{ display: "flex", gap: 0, background: T.panelHi, border: `1px solid ${T.border}`, borderRadius: 6, padding: 3 }}>
          {[
            { id: "verified",  label: `Verified Agents (${verified.length})` },
            { id: "potential", label: `Potential Agents (${potential.length})` },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              style={{ background: tab === t.id ? T.panel : "transparent", border: tab === t.id ? `1px solid ${T.border}` : "1px solid transparent", color: tab === t.id ? T.text : T.textDim, padding: "7px 16px", borderRadius: 4, fontSize: 12, fontFamily: MONO, cursor: "pointer", transition: "all 0.12s" }}>
              {t.label}
            </button>
          ))}
        </div>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agents…"
          style={{ background: T.panelHi, border: `1px solid ${T.border}`, color: T.text, padding: "8px 14px", borderRadius: 4, fontSize: 13, fontFamily: FONT, width: 220 }} />
      </div>

      {/* Context info */}
      {tab === "verified" ? (
        <div style={{ marginBottom: 16, padding: "10px 14px", background: T.accent + "0D", border: `1px solid ${T.accent}33`, borderRadius: 6, fontSize: 12, color: T.textDim }}>
          <span style={{ color: T.accent }}>●</span>&nbsp; Verified agents have been observed making real API calls through the runtime gateway. Confidence: 95%.
        </div>
      ) : (
        <div style={{ marginBottom: 16, padding: "10px 14px", background: T.warn + "0D", border: `1px solid ${T.warn}33`, borderRadius: 6, fontSize: 12, color: T.textDim }}>
          <span style={{ color: T.warn }}>●</span>&nbsp; Potential agents were detected from platform signals (GitHub, Slack, Jira, etc.) but have not yet been confirmed through runtime traffic. Validate or reject each signal.
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div style={{ color: T.textMute, fontFamily: MONO, fontSize: 13, padding: "32px 0", textAlign: "center" }}>Loading agents…</div>
      ) : (
        <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <TH>Agent Name</TH>
                {tab === "verified" ? (
                  <>
                    <TH>Team</TH>
                    <TH>Environment</TH>
                    <TH>Owner</TH>
                    <TH>Last Seen</TH>
                    <TH style={{ textAlign: "right" }}>Monthly Cost</TH>
                    <TH>Status</TH>
                    <TH style={{ textAlign: "right" }}>Actions</TH>
                  </>
                ) : (
                  <>
                    <TH>Source</TH>
                    <TH>Confidence</TH>
                    <TH>First Detected</TH>
                    <TH style={{ textAlign: "right" }}>Actions</TH>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: 32, color: T.textMute, fontFamily: MONO, fontSize: 13 }}>
                    {search ? "No agents match your search" : tab === "verified" ? "No verified agents yet" : "No potential agents to review"}
                  </td>
                </tr>
              ) : filtered.map(agent => {
                const id = agent.agent_id || agent.id;
                const isBusy = busy[id];
                return tab === "verified" ? (
                  <tr key={id}>
                    <TD><span style={{ fontFamily: MONO, color: T.accent }}>{agent.agent_name || agent.agent_id_raw || id}</span></TD>
                    <TD><span style={{ color: T.textDim }}>{agent.team || "—"}</span></TD>
                    <TD>
                      {agent.environment && agent.environment !== "Unknown"
                        ? <span style={{ fontSize: 11, fontFamily: MONO, color: T.info, background: "#0D1F3D", padding: "2px 7px", borderRadius: 3 }}>{agent.environment}</span>
                        : <span style={{ color: T.textMute }}>—</span>}
                    </TD>
                    <TD><span style={{ color: agent.owner ? T.text : T.textMute }}>{agent.owner || "Unassigned"}</span></TD>
                    <TD><span style={{ fontFamily: MONO, color: T.textDim, fontSize: 12 }}>{relativeTime(agent.last_seen_at || agent.last_seen)}</span></TD>
                    <TD style={{ textAlign: "right" }}><span style={{ fontFamily: MONO }}>{fmtUSD(agent.cost_usd || 0)}</span></TD>
                    <TD><LifecycleBadge status={agent.lifecycle_status} /></TD>
                    <TD style={{ textAlign: "right" }}>
                      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                        {(!agent.owner || agent.lifecycle_status === "unassigned") && (
                          <ActionBtn label="Claim" color={T.accent} onClick={() => setClaimAgent(agent)} />
                        )}
                      </div>
                    </TD>
                  </tr>
                ) : (
                  <tr key={id}>
                    <TD><span style={{ fontFamily: MONO, color: T.warn }}>{agent.agent_name || agent.agent_id_raw || id}</span></TD>
                    <TD><SourceBadge source={agent.discovery_source} /></TD>
                    <TD><ConfidenceBadge score={agent.confidence_score} /></TD>
                    <TD><span style={{ fontFamily: MONO, color: T.textDim, fontSize: 12 }}>{relativeTime(agent.first_seen_at || agent.created_at)}</span></TD>
                    <TD style={{ textAlign: "right" }}>
                      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                        <ActionBtn label={isBusy === "validate" ? "…" : "Validate"} color={T.accent} onClick={() => handleValidate(id)} />
                        <ActionBtn label={isBusy === "reject"   ? "…" : "Reject"}   color={T.crit}  onClick={() => handleReject(id)} />
                        <ActionBtn label="Evidence" color={T.info} onClick={() => setEvidenceAgent(agent)} />
                      </div>
                    </TD>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ marginTop: 12, fontSize: 11, color: T.textMute, fontFamily: MONO }}>
        {filtered.length} agent{filtered.length !== 1 ? "s" : ""} shown{search ? ` matching "${search}"` : ""}
      </div>
    </div>
  );
}
