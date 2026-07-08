import React, { useState, useCallback, useEffect } from "react";
import { fetchOrganizations, createOrganization, populateOrganization, clearOrganizationDemoData, deleteOrganization } from "../api.js";
import { isDemoMode, isDevelopment } from "../config.js";
import { T, FONT_MONO } from "../theme.js";

export default function OrganizationsPage() {
  const [orgs,    setOrgs]    = useState([]);
  const [loading, setLoading] = useState(true);
  const [err,     setErr]     = useState(null);
  const [success, setSuccess] = useState(null);

  // Create form
  const [form,    setForm]    = useState({ name: "", admin_email: "", admin_name: "Admin" });
  const [saving,  setSaving]  = useState(false);
  const [created, setCreated] = useState(null); // holds OrgCreated response (has temp password)

  // Populate / clear state — keyed by org id
  const [populating, setPopulating] = useState({});   // { [orgId]: true }
  const [clearing,   setClearing]   = useState({});   // { [orgId]: true }
  const [popResult,  setPopResult]  = useState({});   // { [orgId]: {ok, msg} }

  // Delete org confirmation: org object | null
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleting,      setDeleting]      = useState(false);
  const [deleteErr,     setDeleteErr]     = useState(null);

  const handlePopulate = async (orgId, orgName) => {
    setPopulating(p => ({ ...p, [orgId]: true }));
    setPopResult(r => ({ ...r, [orgId]: null }));
    try {
      const res = await populateOrganization(orgId);
      setPopResult(r => ({ ...r, [orgId]: {
        ok: true,
        msg: `Populated: ${res.assets_upserted} agents · ${res.telemetry_rows_added} telemetry rows · ${res.relationships_created} relationships`,
      }}));
    } catch (e) {
      setPopResult(r => ({ ...r, [orgId]: { ok: false, msg: e.message } }));
    } finally {
      setPopulating(p => ({ ...p, [orgId]: false }));
    }
  };

  const handleClear = async (orgId, orgName) => {
    if (!window.confirm(`Clear all demo data from "${orgName}"?\n\nThis will delete demo telemetry, agents, relationships, and governance rules. Real customer data is not affected.`)) return;
    setClearing(c => ({ ...c, [orgId]: true }));
    setPopResult(r => ({ ...r, [orgId]: null }));
    try {
      const res = await clearOrganizationDemoData(orgId);
      setPopResult(r => ({ ...r, [orgId]: {
        ok: true,
        msg: `Cleared: ${res.telemetry_deleted} telemetry · ${res.assets_deleted} agents · ${res.relationships_deleted} relationships`,
      }}));
    } catch (e) {
      setPopResult(r => ({ ...r, [orgId]: { ok: false, msg: e.message } }));
    } finally {
      setClearing(c => ({ ...c, [orgId]: false }));
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await deleteOrganization(deleteConfirm.id);
      setSuccess(`Organization "${deleteConfirm.name}" deleted.`);
      setDeleteConfirm(null);
      await load();
    } catch (e) {
      setDeleteErr(typeof e.message === 'string' ? e.message : `Delete failed: ${String(e)}`);
    }
    finally { setDeleting(false); }
  };

  const load = useCallback(async () => {
    setErr(null);
    try { setOrgs(await fetchOrganizations()); }
    catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.admin_email.trim()) return;
    setSaving(true); setErr(null); setSuccess(null); setCreated(null);
    try {
      const result = await createOrganization({
        name:           form.name.trim(),
        admin_email:    form.admin_email.trim(),
        admin_name:     form.admin_name.trim() || "Admin",
      });
      setCreated(result);
      setSuccess(`Organization "${result.name}" created.`);
      setForm({ name: "", admin_email: "", admin_name: "Admin" });
      await load();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const fmtDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { year:"numeric", month:"short", day:"numeric" });
  };

  const purple = "#A78BFA";

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:16, maxWidth:900 }}>

      {/* Header */}
      <div>
        <div style={{ fontSize:20, fontWeight:600, color:T.text, letterSpacing:"-0.02em" }}>Organizations</div>
        <div style={{ fontSize:12, color:T.textDim, marginTop:4 }}>Create and manage tenant organizations on this platform. Platform admin access only.</div>
      </div>

      {/* Create form */}
      <div style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:8, padding:"20px 24px" }}>
        <div style={{ fontSize:13, fontWeight:600, color:T.text, marginBottom:4 }}>Create Organization</div>
        <div style={{ fontSize:11, color:T.textMute, marginBottom:16, fontFamily:FONT_MONO }}>
          A default admin user and roles (admin / analyst / viewer) will be created automatically.
        </div>
        <form onSubmit={handleCreate} style={{ display:"flex", gap:12, flexWrap:"wrap", alignItems:"flex-end" }}>
          <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
            <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>Organization Name *</label>
            <input
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Acme Corp"
              required
              style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"7px 12px", borderRadius:4, fontSize:13, fontFamily:FONT_MONO, width:200 }}
            />
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
            <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>Admin Email *</label>
            <input
              type="email"
              value={form.admin_email}
              onChange={e => setForm(f => ({ ...f, admin_email: e.target.value }))}
              placeholder="admin@acme.com"
              required
              style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"7px 12px", borderRadius:4, fontSize:13, fontFamily:FONT_MONO, width:220 }}
            />
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
            <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>Admin Name</label>
            <input
              value={form.admin_name}
              onChange={e => setForm(f => ({ ...f, admin_name: e.target.value }))}
              placeholder="Admin"
              style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"7px 12px", borderRadius:4, fontSize:13, fontFamily:FONT_MONO, width:160 }}
            />
          </div>
          <button type="submit" disabled={saving || !form.name.trim() || !form.admin_email.trim()}
            style={{ background:T.accent, color:T.bg, border:"none", padding:"8px 20px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, fontWeight:600, cursor:"pointer", opacity:(saving||!form.name.trim()||!form.admin_email.trim())?0.5:1, whiteSpace:"nowrap", height:34, alignSelf:"flex-end" }}>
            {saving ? "Creating…" : "+ Create Organization"}
          </button>
        </form>

        {err && (
          <div style={{ marginTop:12, color:T.crit, fontFamily:FONT_MONO, fontSize:12, background:`${T.crit}10`, border:`1px solid ${T.crit}33`, borderRadius:4, padding:"8px 12px" }}>{err}</div>
        )}

        {success && created && (
          <div style={{ marginTop:12, background:`${T.accent}10`, border:`1px solid ${T.accent}44`, borderRadius:6, padding:"14px 16px", display:"flex", flexDirection:"column", gap:8 }}>
            <div style={{ fontSize:13, color:T.accent, fontWeight:600 }}>✓ {success}</div>
            <div style={{ fontSize:11, color:T.textDim, fontFamily:FONT_MONO }}>Default roles (admin / analyst / viewer) were created for this organization.</div>
            {created.admin_temporary_password && (
              <div style={{ background:T.bg, border:`1px solid ${T.warn}44`, borderRadius:4, padding:"10px 14px" }}>
                <div style={{ fontSize:9, fontFamily:FONT_MONO, color:T.warn, letterSpacing:"0.12em", textTransform:"uppercase", marginBottom:6 }}>Temporary Admin Password — copy now, not shown again</div>
                <div style={{ fontFamily:FONT_MONO, fontSize:13, color:T.text, letterSpacing:"0.05em" }}>{created.admin_temporary_password}</div>
                <div style={{ fontSize:10, color:T.textMute, fontFamily:FONT_MONO, marginTop:6 }}>
                  Admin: {created.admin_email} · Org: {created.name} (slug: {created.slug})
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Organizations table */}
      <div style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:8, overflow:"hidden" }}>
        <div style={{ padding:"16px 20px", borderBottom:`1px solid ${T.border}`, display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div style={{ fontSize:13, fontWeight:600, color:T.text }}>
            All Organizations
            {orgs.length > 0 && <span style={{ fontFamily:FONT_MONO, fontSize:11, color:T.textMute, marginLeft:8 }}>· {orgs.length}</span>}
          </div>
          <button onClick={load} style={{ background:"transparent", border:`1px solid ${T.border}`, color:T.textDim, padding:"4px 12px", borderRadius:4, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer" }}>
            Refresh
          </button>
        </div>

        {loading ? (
          <div style={{ color:T.textMute, fontFamily:FONT_MONO, fontSize:12, padding:"24px 20px" }}>Loading organizations…</div>
        ) : orgs.length === 0 ? (
          <div style={{ padding:"32px 20px", textAlign:"center" }}>
            <div style={{ fontSize:24, color:T.textMute, marginBottom:12 }}>◻</div>
            <div style={{ fontSize:14, color:T.textDim, marginBottom:6 }}>No organizations created yet.</div>
            <div style={{ fontSize:12, color:T.textMute, fontFamily:FONT_MONO }}>Create your first customer organization to start onboarding AI assets.</div>
          </div>
        ) : (
          <table style={{ width:"100%", borderCollapse:"collapse" }}>
            <thead>
              <tr style={{ borderBottom:`1px solid ${T.border}` }}>
                {["ID","Name","Slug","Created","Users",""].map(h => (
                  <th key={h} style={{ textAlign:"left", padding:"10px 16px", fontFamily:FONT_MONO, fontSize:10, letterSpacing:"0.1em", textTransform:"uppercase", color:T.textMute, fontWeight:500, background:T.panelHi }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orgs.map(o => (
                <tr key={o.id} style={{ borderBottom:`1px solid ${T.border}` }}>
                  <td style={{ padding:"14px 16px", fontFamily:FONT_MONO, fontSize:11, color:T.textMute }}>{o.id}</td>
                  <td style={{ padding:"14px 16px", fontSize:13, color:T.text, fontWeight:500 }}>
                    {o.name}
                    {o.is_internal && (
                      <span style={{ marginLeft:8, fontSize:9, fontFamily:FONT_MONO, color:purple, background:`${purple}18`, border:`1px solid ${purple}44`, borderRadius:3, padding:"1px 6px", textTransform:"uppercase", letterSpacing:"0.08em" }}>platform</span>
                    )}
                  </td>
                  <td style={{ padding:"14px 16px", fontFamily:FONT_MONO, fontSize:12, color:T.textDim }}>{o.slug || "—"}</td>
                  <td style={{ padding:"14px 16px", fontSize:12, color:T.textDim }}>{fmtDate(o.created_at)}</td>
                  <td style={{ padding:"14px 16px", fontSize:12, color:T.textDim, fontFamily:FONT_MONO }}>{o.user_count ?? "—"}</td>
                  <td style={{ padding:"10px 16px" }}>
                    <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
                      <div style={{ display:"flex", gap:6, flexWrap:"wrap" }}>
                        {!o.is_internal && (isDemoMode() || isDevelopment()) && (
                          <>
                            <button
                              onClick={() => handlePopulate(o.id, o.name)}
                              disabled={populating[o.id] || clearing[o.id]}
                              title="Seed realistic enterprise data: teams, agents, telemetry, relationships, budgets"
                              style={{ background:T.accent, color:T.bg, border:"none", padding:"5px 12px", borderRadius:4, fontSize:11, fontFamily:FONT_MONO, fontWeight:600, cursor:"pointer", opacity:(populating[o.id]||clearing[o.id])?0.5:1, whiteSpace:"nowrap" }}>
                              {populating[o.id] ? "Populating…" : "Populate"}
                            </button>
                            <button
                              onClick={() => handleClear(o.id, o.name)}
                              disabled={populating[o.id] || clearing[o.id]}
                              title="Remove all demo data (is_demo=true) from this organization"
                              style={{ background:"transparent", color:T.warn, border:`1px solid ${T.warn}55`, padding:"5px 12px", borderRadius:4, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer", opacity:(populating[o.id]||clearing[o.id])?0.5:1, whiteSpace:"nowrap" }}>
                              {clearing[o.id] ? "Clearing…" : "Clear Demo"}
                            </button>
                          </>
                        )}
                        {!o.is_internal && (
                          <button
                            onClick={() => setDeleteConfirm(o)}
                            title="Permanently delete this organization and all its data"
                            style={{ background:"transparent", color:T.crit, border:`1px solid ${T.crit}55`, padding:"5px 12px", borderRadius:4, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer", whiteSpace:"nowrap" }}>
                            Delete
                          </button>
                        )}
                      </div>
                      {popResult[o.id] && (
                        <div style={{ fontSize:10, fontFamily:FONT_MONO, color: popResult[o.id].ok ? T.accent : T.crit, maxWidth:320 }}>
                          {popResult[o.id].ok ? "✓ " : "✗ "}{popResult[o.id].msg}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {/* ── Delete Confirmation Modal ── */}
      {deleteConfirm && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.65)", display:"flex", alignItems:"center", justifyContent:"center", zIndex:1000 }}>
          <div style={{ background:T.panel, border:`1px solid ${T.crit}55`, borderRadius:10, padding:28, minWidth:360, maxWidth:460, display:"flex", flexDirection:"column", gap:18 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10 }}>
              <span style={{ fontSize:22, color:T.crit }}>⊗</span>
              <div style={{ fontWeight:700, color:T.text, fontSize:15 }}>Delete organization?</div>
            </div>
            <div style={{ fontSize:13, color:T.textDim, lineHeight:1.6 }}>
              You are about to permanently delete{" "}
              <strong style={{ color:T.text }}>{deleteConfirm.name}</strong> and all its data — users,
              agents, telemetry, budgets, policies, and relationships.{" "}
              <span style={{ color:T.crit, fontWeight:600 }}>This cannot be undone.</span>
            </div>
            <div style={{ background:`${T.crit}0d`, border:`1px solid ${T.crit}33`, borderRadius:5, padding:"10px 14px", fontFamily:FONT_MONO, fontSize:11, color:T.crit }}>
              Org: {deleteConfirm.name} · ID: {deleteConfirm.id} · Slug: {deleteConfirm.slug}
            </div>
            {deleteErr && (
              <div style={{ color:T.crit, fontFamily:FONT_MONO, fontSize:12, background:`${T.crit}10`, border:`1px solid ${T.crit}33`, borderRadius:4, padding:"8px 12px" }}>{deleteErr}</div>
            )}
            <div style={{ display:"flex", gap:10, justifyContent:"flex-end" }}>
              <button onClick={() => { setDeleteConfirm(null); setDeleteErr(null); }} disabled={deleting}
                style={{ background:"transparent", border:`1px solid ${T.border}`, color:T.textDim, padding:"8px 20px", borderRadius:5, fontSize:12, fontFamily:FONT_MONO, cursor:"pointer" }}>
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleting}
                style={{ background:T.crit, color:"#fff", border:"none", padding:"8px 20px", borderRadius:5, fontSize:12, fontFamily:FONT_MONO, fontWeight:700, cursor:"pointer", opacity:deleting?0.6:1 }}>
                {deleting ? "Deleting…" : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
