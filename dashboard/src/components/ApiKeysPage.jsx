import React, { useState, useCallback, useEffect } from "react";
import { fetchApiKeys, createApiKey, revokeApiKey, deleteApiKey, fetchApiKeyAgents } from "../api.js";
import { gatewayBaseUrl, PUBLIC_APP_URL, PUBLIC_DEMO_URL } from "../config.js";
import { T, FONT_MONO } from "../theme.js";
import { Card, Pill } from "./ui.jsx";

export default function ApiKeysPage({ demoMode = false }) {
  const [keys,      setKeys]      = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [form,      setForm]      = useState({ name: "", team: "", purpose: "otel" });
  const [saving,    setSaving]    = useState(false);
  const [err,       setErr]       = useState(null);
  const [newKey,    setNewKey]    = useState(null); // shown-once modal
  const [expanded,  setExpanded]  = useState(null); // key id whose agents are shown
  const [agents,    setAgents]    = useState({});   // { [id]: { loading, rows, error } }

  const toggleAgents = useCallback(async (id) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    if (agents[id]) return; // already loaded
    setAgents(a => ({ ...a, [id]: { loading: true } }));
    try {
      const data = await fetchApiKeyAgents(id);
      setAgents(a => ({ ...a, [id]: { loading: false, rows: data.agents } }));
    } catch (e) {
      setAgents(a => ({ ...a, [id]: { loading: false, error: e.message } }));
    }
  }, [expanded, agents]);

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
      const created = await createApiKey({ name: form.name.trim(), team: form.team.trim() || "unknown", purpose: form.purpose });
      setNewKey(created.key);
      setForm({ name: "", team: "", purpose: form.purpose });
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

  const fmtDate = (d) => d ? new Date(d).toLocaleString("en-US") : "—";

  const inputStyle = { background: T.panelHi, color: T.text, border: `1px solid ${T.border}`,
    padding: "6px 10px", borderRadius: 4, fontSize: 12, fontFamily: FONT_MONO, width: 200 };

  if (loading) return <div style={{ color: T.textDim, fontFamily: FONT_MONO, padding: 24 }}>Loading…</div>;

  const otelKeys    = keys.filter(k => (k.purpose || "otel") !== "gateway");
  const gatewayKeys = keys.filter(k => k.purpose === "gateway");

  // Plain render helper (not a component) — one keys table, optionally with the
  // per-key "agents seen" expander (only meaningful for OTLP ingestion keys).
  const renderKeysCard = (title, list, { showAgents, emptyMsg }) => (
    <Card title={`${title} · ${list.length}`}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            {["Name", "Prefix", "Team", "Created", "Last Used", "Status", ""].map(h => (
              <th key={h} style={{ padding: "10px 8px", textAlign: "left", fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.1em", textTransform: "uppercase", color: T.textMute }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.length === 0 && (
            <tr><td colSpan={7} style={{ padding: 20, textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 12 }}>{emptyMsg}</td></tr>
          )}
          {list.map(k => (
            <React.Fragment key={k.id}>
            <tr style={{ borderBottom: `1px solid ${T.border}`, opacity: k.is_active ? 1 : 0.45 }}>
              <td style={{ padding: "12px 8px", fontSize: 12, color: T.text, fontWeight: 500 }}>
                {showAgents ? (
                  <button onClick={() => toggleAgents(k.id)} title="Agents seen on this key"
                    style={{ background: "transparent", border: "none", color: T.text, fontSize: 12, fontWeight: 500, fontFamily: "inherit", cursor: "pointer", padding: 0, display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 10 }}>{expanded === k.id ? "▾" : "▸"}</span>
                    {k.name}
                  </button>
                ) : k.name}
              </td>
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
            {showAgents && expanded === k.id && (
              <tr style={{ borderBottom: `1px solid ${T.border}`, background: T.panelHi }}>
                <td colSpan={7} style={{ padding: "10px 8px 14px 26px" }}>
                  <div style={{ fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.1em", textTransform: "uppercase", color: T.textMute, marginBottom: 8 }}>
                    Agents seen on this key
                  </div>
                  {(() => {
                    const st = agents[k.id] || {};
                    if (st.loading) return <div style={{ fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>Loading…</div>;
                    if (st.error)   return <div style={{ fontSize: 12, color: T.crit, fontFamily: FONT_MONO }}>{st.error}</div>;
                    const rows = st.rows || [];
                    if (rows.length === 0) return (
                      <div style={{ fontSize: 12, color: T.textMute }}>
                        No agents attributed to this key yet — attribution begins with new traffic. Agent names come from <strong style={{ color: T.textDim }}>service.name</strong> once your Collector sends traces.
                      </div>
                    );
                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {rows.map(a => (
                          <div key={a.service_name} style={{ display: "flex", gap: 14, alignItems: "baseline", fontSize: 12 }}>
                            <span style={{ color: T.text, fontFamily: FONT_MONO, minWidth: 220 }}>{a.service_name}</span>
                            <span style={{ color: T.textDim }}>{a.span_count} spans</span>
                            <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>last seen {fmtDate(a.last_seen)}</span>
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                </td>
              </tr>
            )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </Card>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

      {/* ── Page header ── */}
      <div>
        <div style={{ fontSize: 20, fontWeight: 500, color: T.text, letterSpacing: "-0.01em" }}>API Keys</div>
        <div style={{ fontSize: 12, color: T.textDim, marginTop: 4 }}>
          Use this key to <strong style={{ color: T.text }}>send OpenTelemetry traces</strong> to ObserveAgents — it's your Bearer token for OTLP ingestion.
          The same key can optionally route traffic through the Gateway. Each key is shown once — copy it immediately.
        </div>
      </div>

      {/* ── Create key ── */}
      <Card title="New API Key">
        <form onSubmit={handleCreate} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 9, fontFamily: FONT_MONO, letterSpacing: "0.12em", textTransform: "uppercase", color: T.textMute }}>Purpose *</label>
            <select value={form.purpose} onChange={e => setForm({ ...form, purpose: e.target.value })}
              style={{ ...inputStyle, width: 220, cursor: "pointer" }}>
              <option value="otel">OTLP ingestion (Collector)</option>
              <option value="gateway">Gateway routing (per app)</option>
            </select>
          </div>
          {[
            { label: "Name *", key: "name", placeholder: form.purpose === "gateway" ? "e.g. customer-support-prod" : "e.g. prod-otel-collector" },
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
          {form.purpose === "gateway"
            ? <>Gateway routing keys are <strong style={{ color: T.textDim }}>per app / workflow</strong> — each app routes its LLM traffic through the Gateway with its own key (e.g. customer-support-prod, sales-assistant-prod).</>
            : <>One key per Collector — usually a single key for your whole organization. Agent names come automatically from <strong style={{ color: T.textDim }}>service.name</strong> in your traces, so you don't need a key per agent. Add more only for extra Collectors or separate environments (staging/prod).</>}
        </div>
        {err && <div style={{ color: T.crit, fontFamily: FONT_MONO, fontSize: 12, marginTop: 10 }}>{err}</div>}
      </Card>

      {/* ── OTLP ingestion keys (Collector) ── */}
      {renderKeysCard("OTLP Ingestion Keys", otelKeys, {
        showAgents: true,
        emptyMsg: "No ingestion keys yet.",
      })}

      {/* ── Gateway routing keys (per app) ── */}
      {renderKeysCard("Gateway Routing Keys", gatewayKeys, {
        showAgents: false,
        emptyMsg: "No Gateway routing keys. Create one per app only if you route LLM traffic through the Gateway.",
      })}

      {/* ── Show-once modal + first-request onboarding ── */}
      {newKey && (() => {
        // demoMode comes from props (main's fix so the demo build never
        // shows the production gateway/observe host); both snippets honor it.
        const observeUrl = demoMode ? PUBLIC_DEMO_URL : PUBLIC_APP_URL;
        const gatewayUrl = gatewayBaseUrl(demoMode);
        const otelSnippet = `# Point your OpenTelemetry exporter at ObserveAgents
OTEL_EXPORTER_OTLP_ENDPOINT=${observeUrl}/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer ${newKey}
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_SERVICE_NAME=my-agent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production`;
        const gatewaySnippet = `from openai import OpenAI

client = OpenAI(
    api_key="${newKey}",
    base_url="${gatewayUrl}/v1"
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}]
)`;
        const outcomes = [
          "Agent discovered from runtime evidence",
          "Runtime timeline populated",
          "Capabilities & dependencies mapped",
          "Security findings derived",
          "Owner & control suggestions surfaced",
        ];
        return (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24, overflowY: "auto" }}>
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

            {/* Next step: send your first OpenTelemetry trace (primary path) */}
            <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
              <div style={{ fontSize: 9, fontFamily: FONT_MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 4 }}>Next Step · OpenTelemetry</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>Send your first trace.</div>
              <div style={{ fontSize: 12, color: T.textDim, marginBottom: 12 }}>
                Point your existing OpenTelemetry exporter at ObserveAgents — no proprietary SDK — using this key as the Bearer token.
                Then open <strong style={{ color: T.text }}>Runtime</strong> and watch your first trace appear.
              </div>
              <div style={{ position: "relative" }}>
                <pre style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 6, padding: "14px 16px", fontFamily: FONT_MONO, fontSize: 11.5, color: T.text, margin: 0, overflowX: "auto", lineHeight: 1.6 }}>{otelSnippet}</pre>
                <button onClick={() => navigator.clipboard.writeText(otelSnippet).catch(() => {})}
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

            {/* Optional path: route through the Gateway */}
            <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
              <div style={{ fontSize: 9, fontFamily: FONT_MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 4 }}>Optional · Gateway</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>Prefer not to instrument? Route through the Gateway.</div>
              <div style={{ fontSize: 12, color: T.textDim, marginBottom: 12 }}>
                Change one line — your OpenAI <code style={{ fontFamily: FONT_MONO, fontSize: 11, color: T.accent }}>base_url</code> — to send traffic through the Gateway with the same key. Observe-only until you configure control.
              </div>
              <div style={{ position: "relative" }}>
                <pre style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 6, padding: "14px 16px", fontFamily: FONT_MONO, fontSize: 11.5, color: T.text, margin: 0, overflowX: "auto", lineHeight: 1.6 }}>{gatewaySnippet}</pre>
                <button onClick={() => navigator.clipboard.writeText(gatewaySnippet).catch(() => {})}
                  style={{ position: "absolute", top: 8, right: 8, background: `${T.accent}20`, border: `1px solid ${T.accent}55`, color: T.accent, padding: "3px 10px", borderRadius: 4, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer" }}>
                  Copy
                </button>
              </div>
            </div>

            {/* Key vs credential clarity */}
            <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>Your API Key</div>
                <div style={{ fontSize: 12, color: T.textDim }}>Sends OpenTelemetry traces to ObserveAgents, and optionally routes traffic through the Gateway.</div>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>Provider Credentials</div>
                <div style={{ fontSize: 12, color: T.textDim }}>Only needed for the Gateway path. Stored securely by ObserveAgents — never place provider keys in your app.</div>
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
