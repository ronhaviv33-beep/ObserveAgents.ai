import React, { useState, useCallback, useEffect } from "react";
import { fetchApiKeys, createApiKey, revokeApiKey, deleteApiKey } from "../api.js";
import { gatewayBaseUrl } from "../config.js";
import { T, FONT_MONO } from "../theme.js";
import { Card, Pill } from "./ui.jsx";

export default function ApiKeysPage() {
  const [keys,      setKeys]      = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [form,      setForm]      = useState({ name: "", team: "" });
  const [saving,    setSaving]    = useState(false);
  const [err,       setErr]       = useState(null);
  const [newKey,    setNewKey]    = useState(null); // shown-once modal

  const load = useCallback(async () => {
    try { setKeys(await fetchApiKeys()); }
    catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setErr("Name is required."); return; }
    setSaving(true); setErr(null);
    try {
      const created = await createApiKey({ name: form.name.trim(), team: form.team.trim() || "unknown" });
      setNewKey(created.key);
      setForm({ name: "", team: "" });
      await load();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const handleRevoke = async (id) => {
    try { await revokeApiKey(id); await load(); }
    catch (e) { setErr(e.message); }
  };

  const handleDelete = async (id) => {
    try { await deleteApiKey(id); await load(); }
    catch (e) { setErr(e.message); }
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleString() : "—";

  const inputStyle = { background: T.panelHi, color: T.text, border: `1px solid ${T.border}`,
    padding: "6px 10px", borderRadius: 4, fontSize: 12, fontFamily: FONT_MONO, width: 200 };

  if (loading) return <div style={{ color: T.textDim, fontFamily: FONT_MONO, padding: 24 }}>Loading…</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

      {/* ── Page header ── */}
      <div>
        <div style={{ fontSize: 20, fontWeight: 500, color: T.text, letterSpacing: "-0.01em" }}>Gateway API Keys</div>
        <div style={{ fontSize: 12, color: T.textDim, marginTop: 4 }}>
          Use these keys <strong style={{ color: T.text }}>inside your AI applications</strong> to route traffic through the gateway.
          Do not use your OpenAI key when routing through the gateway. Each key is shown once — copy it immediately.
        </div>
      </div>

      {/* ── Create key ── */}
      <Card title="New Gateway API Key">
        <form onSubmit={handleCreate} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          {[
            { label: "Name *", key: "name", placeholder: "e.g. customer-support-prod" },
            { label: "Team",   key: "team", placeholder: "e.g. Customer Success" },
          ].map(({ label, key, placeholder }) => (
            <div key={key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={{ fontSize: 9, fontFamily: FONT_MONO, letterSpacing: "0.12em", textTransform: "uppercase", color: T.textMute }}>{label}</label>
              <input type="text" placeholder={placeholder} value={form[key]}
                onChange={e => setForm({ ...form, [key]: e.target.value })}
                style={inputStyle} />
            </div>
          ))}
          <button type="submit" disabled={saving}
            style={{ background: T.accent, color: T.bg, border: "none", padding: "8px 18px", borderRadius: 4, fontSize: 12, fontFamily: FONT_MONO, fontWeight: 600, cursor: "pointer", opacity: saving ? 0.6 : 1 }}>
            {saving ? "Generating…" : "+ Generate"}
          </button>
        </form>
        <div style={{ fontSize: 11, color: T.textMute, fontFamily: FONT_MONO, marginTop: 10 }}>
          Create one Gateway API Key per service, workflow or AI application — e.g. customer-support-prod, sales-assistant-prod, engineering-copilot, platform-agent.
        </div>
        {err && <div style={{ color: T.crit, fontFamily: FONT_MONO, fontSize: 12, marginTop: 10 }}>{err}</div>}
      </Card>

      {/* ── Keys table ── */}
      <Card title={`Keys · ${keys.length}`}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${T.border}` }}>
              {["Name", "Prefix", "Team", "Created", "Last Used", "Status", ""].map(h => (
                <th key={h} style={{ padding: "10px 8px", textAlign: "left", fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.1em", textTransform: "uppercase", color: T.textMute }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 && (
              <tr><td colSpan={7} style={{ padding: 20, textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 12 }}>No API keys yet.</td></tr>
            )}
            {keys.map(k => (
              <tr key={k.id} style={{ borderBottom: `1px solid ${T.border}`, opacity: k.is_active ? 1 : 0.45 }}>
                <td style={{ padding: "12px 8px", fontSize: 12, color: T.text, fontWeight: 500 }}>{k.name}</td>
                <td style={{ padding: "12px 8px", fontFamily: FONT_MONO, fontSize: 11, color: T.textDim }}>{k.key_prefix}…</td>
                <td style={{ padding: "12px 8px", fontSize: 12, color: T.textDim }}>{k.team}</td>
                <td style={{ padding: "12px 8px", fontFamily: FONT_MONO, fontSize: 11, color: T.textMute }}>{fmtDate(k.created_at)}</td>
                <td style={{ padding: "12px 8px", fontFamily: FONT_MONO, fontSize: 11, color: T.textMute }}>{fmtDate(k.last_used_at)}</td>
                <td style={{ padding: "12px 8px" }}>
                  {k.is_active ? <Pill color={T.accent}>active</Pill> : <Pill color={T.textMute}>revoked</Pill>}
                </td>
                <td style={{ padding: "10px 8px" }}>
                  <div style={{ display: "flex", gap: 6 }}>
                    {k.is_active && (
                      <button onClick={() => handleRevoke(k.id)}
                        style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.warn, padding: "4px 10px", borderRadius: 3, fontSize: 11, fontFamily: FONT_MONO, cursor: "pointer" }}>
                        Revoke
                      </button>
                    )}
                    <button onClick={() => handleDelete(k.id)}
                      style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.crit, padding: "4px 10px", borderRadius: 3, fontSize: 11, fontFamily: FONT_MONO, cursor: "pointer" }}>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* ── Show-once modal + first-request onboarding ── */}
      {newKey && (() => {
        const gatewayUrl = gatewayBaseUrl();
        const snippet = `from openai import OpenAI

client = OpenAI(
    api_key="${newKey}",
    base_url="${gatewayUrl}/v1"
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}]
)`;
        const outcomes = [
          "Agent discovered",
          "Cost tracking enabled",
          "Dependency mapping enabled",
          "Governance enabled",
          "Ownership suggestions enabled",
        ];
        return (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24, overflowY: "auto" }}>
          <div style={{ background: T.panel, border: `1px solid ${T.accent}66`, borderRadius: 8, padding: 28, maxWidth: 600, width: "100%", display: "flex", flexDirection: "column", gap: 16, margin: "auto" }}>
            <div style={{ fontFamily: FONT_MONO, fontWeight: 700, color: T.accent, fontSize: 14 }}>Copy your key — shown once only</div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: T.textDim }}>
              This will not be shown again. Store it in your secrets manager now.
            </div>
            <div style={{ background: T.panelHi, border: `1px solid ${T.border}`, borderRadius: 4, padding: "10px 14px", fontFamily: FONT_MONO, fontSize: 12, color: T.text, wordBreak: "break-all", userSelect: "all" }}>
              {newKey}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={() => navigator.clipboard.writeText(newKey).catch(() => {})}
                style={{ background: `${T.accent}20`, border: `1px solid ${T.accent}55`, color: T.accent, padding: "7px 16px", borderRadius: 4, fontSize: 12, fontFamily: FONT_MONO, cursor: "pointer" }}>
                Copy key
              </button>
            </div>

            {/* Next step: send your first AI request */}
            <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
              <div style={{ fontSize: 9, fontFamily: FONT_MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 4 }}>Next Step</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>Send your first AI request.</div>
              <div style={{ fontSize: 12, color: T.textDim, marginBottom: 12 }}>
                Use this Gateway API Key inside your AI application — replace your OpenAI endpoint with the gateway endpoint.
              </div>
              <div style={{ position: "relative" }}>
                <pre style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 6, padding: "14px 16px", fontFamily: FONT_MONO, fontSize: 11.5, color: T.text, margin: 0, overflowX: "auto", lineHeight: 1.6 }}>{snippet}</pre>
                <button onClick={() => navigator.clipboard.writeText(snippet).catch(() => {})}
                  style={{ position: "absolute", top: 8, right: 8, background: `${T.accent}20`, border: `1px solid ${T.accent}55`, color: T.accent, padding: "3px 10px", borderRadius: 4, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer" }}>
                  Copy
                </button>
              </div>
              <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 6 }}>
                {outcomes.map(o => (
                  <div key={o} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: T.textDim }}>
                    <span style={{ color: T.accent }}>✓</span>{o}
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12, fontSize: 11, fontFamily: FONT_MONO, color: T.textMute }}>Estimated setup time: 30 seconds</div>
            </div>

            {/* Key vs credential clarity */}
            <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>Gateway API Key</div>
                <div style={{ fontSize: 12, color: T.textDim }}>Used by your applications to route traffic through the gateway.</div>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>Provider Credentials</div>
                <div style={{ fontSize: 12, color: T.textDim }}>Stored securely by ObserveAgents. Never place OpenAI keys in customer code.</div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button onClick={() => setNewKey(null)}
                style={{ background: T.accent, color: T.bg, border: "none", padding: "7px 18px", borderRadius: 4, fontSize: 12, fontFamily: FONT_MONO, fontWeight: 600, cursor: "pointer" }}>
                I've saved it — close
              </button>
            </div>
          </div>
        </div>
        );
      })()}
    </div>
  );
}
