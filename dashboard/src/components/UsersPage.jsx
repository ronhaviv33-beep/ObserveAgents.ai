import React, { useState, useCallback, useEffect } from "react";
import { fetchUsers, createUser, updateUser, deleteUser, fetchRoles } from "../api.js";
import { T, FONT_MONO } from "../theme.js";
import { Card, Pill, useSortable, useSearch, SearchBox, SortableTh } from "./ui.jsx";
import { useUser, useRoles } from "../auth.jsx";

function SortableUsersTable({ users, currentUser, editing, editSaving, setEditing, saveEdit, cancelEdit, handleToggle, handleDelete, onDisable, inlineInput, inlineSelect, onChangePassword }) {
  const roles = useRoles();
  const { sortKey, sortDir, toggle, sort } = useSortable("created_at");
  const colKey = { "Name":"name","Email":"email","Role":"role","Team":"team","Status":"is_active","Created":"created_at" };
  const sorted = sort(users, (u, k) => {
    if (k === "created_at") return new Date(u.created_at).getTime();
    if (k === "is_active")  return u.is_active ? 1 : 0;
    return u[k] || "";
  });
  const { query, setQuery, filtered } = useSearch(sorted, u => `${u.name} ${u.email} ${u.role} ${u.team||""}`);
  return (
    <>
    <SearchBox query={query} onChange={setQuery} placeholder="Search name, email, role, team…" count={filtered.length} total={users.length} />
    <table style={{ width:"100%", borderCollapse:"collapse" }}>
      <thead>
        <tr style={{ borderBottom:`1px solid ${T.border}` }}>
          {["Name","Email","Role","Team","Status","Created",""].map(h => h === "" ? (
            <th key={h} style={{ padding:"10px 8px" }} />
          ) : (
            <SortableTh key={h} label={h} sortKey={colKey[h]} active={sortKey===colKey[h]} dir={sortDir} onToggle={toggle} />
          ))}
        </tr>
      </thead>
      <tbody>
        {filtered.map(u => {
          const isEditing = editing?.id === u.id;
          const isSelf    = u.id === currentUser?.id;
          return (
            <tr key={u.id} style={{ borderBottom:`1px solid ${T.border}`, opacity:u.is_active?1:0.5, background: isEditing ? `${T.accent}06` : "transparent" }}>
              <td style={{ padding:"12px 8px", fontSize:12, color:T.text, fontWeight:500 }}>{u.name}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:11, color:T.textDim }}>{u.email}</td>
              <td style={{ padding:"10px 8px" }}>
                {isEditing
                  ? inlineSelect(editing.role, v => setEditing({...editing, role:v}), Object.entries(roles).map(([r, m]) => [r, m.label]))
                  : <Pill color={roles[u.role]?.color ?? T.textDim}>{u.role}</Pill>}
              </td>
              <td style={{ padding:"10px 8px" }}>
                {isEditing
                  ? inlineInput(editing.team, v => setEditing({...editing, team:v}), 90)
                  : <span style={{ fontSize:12, color:T.textDim }}>{u.team || "—"}</span>}
              </td>
              <td style={{ padding:"12px 8px" }}>{u.is_active ? <Pill color={T.accent}>active</Pill> : <Pill color={T.textMute}>inactive</Pill>}</td>
              <td style={{ padding:"12px 8px", fontFamily:FONT_MONO, fontSize:11, color:T.textMute }}>{new Date(u.created_at).toLocaleDateString("en-US")}</td>
              <td style={{ padding:"10px 8px" }}>
                <div style={{ display:"flex", gap:6, flexWrap:"nowrap" }}>
                  {isEditing ? (
                    <>
                      <button onClick={saveEdit} disabled={editSaving}
                        style={{ background:`${T.accent}20`, border:`1px solid ${T.accent}55`, color:T.accent, padding:"4px 12px", borderRadius:3, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer", fontWeight:600, opacity:editSaving?0.6:1 }}>
                        {editSaving ? "…" : "Save"}
                      </button>
                      <button onClick={cancelEdit}
                        style={{ background:"transparent", border:`1px solid ${T.border}`, color:T.textDim, padding:"4px 10px", borderRadius:3, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer" }}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button onClick={() => setEditing({ id: u.id, role: u.role, team: u.team || "" })}
                        style={{ background:`${T.info}15`, border:`1px solid ${T.info}44`, color:T.info, padding:"4px 10px", borderRadius:3, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer" }}>
                        Edit
                      </button>
                      <button onClick={() => onChangePassword && onChangePassword(u)}
                        style={{ background:`${T.accent}12`, border:`1px solid ${T.accent}44`, color:T.accent, padding:"4px 10px", borderRadius:3, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer" }}>
                        Password
                      </button>
                      <button onClick={() => u.is_active ? onDisable(u) : handleToggle(u)}
                        style={{ background:"transparent", border:`1px solid ${T.border}`, color:u.is_active?T.warn:T.accent, padding:"4px 10px", borderRadius:3, fontSize:11, fontFamily:FONT_MONO, cursor:"pointer" }}>
                        {u.is_active ? "Disable" : "Enable"}
                      </button>
                      <button onClick={() => handleDelete(u.id)} disabled={isSelf}
                        style={{ background:"transparent", border:`1px solid ${T.border}`, color:isSelf?T.textMute:T.crit, padding:"4px 10px", borderRadius:3, fontSize:11, fontFamily:FONT_MONO, cursor:isSelf?"not-allowed":"pointer", opacity:isSelf?0.4:1 }}
                        title={isSelf ? "Cannot delete your own account" : ""}>
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
    </>
  );
}

export default function UsersPage() {
  const currentUser = useUser();
  const rolesMap = useRoles();
  const [serverRoles, setServerRoles] = useState(null); // null = not yet loaded
  const roles = serverRoles
    ? Object.fromEntries(serverRoles.map(r => [r.name, r]))
    : rolesMap;
  const [users,    setUsers]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [form,     setForm]     = useState({ email:"", name:"", password:"", role:"analyst", team:"" });
  const [saving,   setSaving]   = useState(false);
  const [err,      setErr]      = useState(null);
  // editing: { id, role, team } | null
  const [editing,  setEditing]  = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  // password change modal: { id, name } | null
  const [pwModal,   setPwModal]   = useState(null);
  const [pwOld,     setPwOld]     = useState("");
  const [pwNew,     setPwNew]     = useState("");
  const [pwConfirm, setPwConfirm] = useState("");
  const [pwSaving,  setPwSaving]  = useState(false);
  const [pwErr,     setPwErr]     = useState(null);
  // disable confirmation: user object | null
  const [disableConfirm, setDisableConfirm] = useState(null);

  const load = useCallback(async () => {
    try {
      const [data, roleData] = await Promise.all([fetchUsers(), fetchRoles().catch(() => null)]);
      setUsers(data);
      if (roleData) setServerRoles(roleData);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setSaving(true); setErr(null);
    try {
      await createUser(form);
      setForm({ email:"", name:"", password:"", role:"analyst", team:"" });
      await load();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const handleToggle = async (u) => {
    try { await updateUser(u.id, { is_active: !u.is_active }); await load(); }
    catch (e) { setErr(e.message); }
  };

  const handleDelete = async (id) => {
    try { await deleteUser(id); await load(); }
    catch (e) { setErr(e.message); }
  };

  const startEdit = (u) => setEditing({ id: u.id, role: u.role, team: u.team || "" });
  const cancelEdit = () => setEditing(null);

  const saveEdit = async () => {
    setEditSaving(true); setErr(null);
    try {
      await updateUser(editing.id, { role: editing.role, team: editing.team });
      setEditing(null);
      await load();
    } catch (e) { setErr(e.message); }
    finally { setEditSaving(false); }
  };

  const openPwModal = (u) => { setPwModal(u); setPwOld(""); setPwNew(""); setPwConfirm(""); setPwErr(null); };
  const closePwModal = () => { setPwModal(null); setPwOld(""); setPwNew(""); setPwConfirm(""); setPwErr(null); };

  const savePassword = async () => {
    if (!pwOld) { setPwErr("Current password is required."); return; }
    if (pwNew.length < 8) { setPwErr("New password must be at least 8 characters."); return; }
    if (pwNew !== pwConfirm) { setPwErr("Passwords do not match."); return; }
    setPwSaving(true); setPwErr(null);
    try {
      await updateUser(pwModal.id, { password: pwNew, current_password: pwOld });
      closePwModal();
    } catch (e) { setPwErr(e.message); }
    finally { setPwSaving(false); }
  };

  const inlineInput = (val, onChange, width = 100) => (
    <input value={val} onChange={e => onChange(e.target.value)}
      style={{ background:T.bg, color:T.text, border:`1px solid ${T.accent}44`, padding:"4px 8px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, width }} />
  );

  const inlineSelect = (val, onChange, options) => (
    <select value={val} onChange={e => onChange(e.target.value)}
      style={{ background:T.bg, color:T.text, border:`1px solid ${T.accent}44`, padding:"4px 8px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO }}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );

  if (loading) return <div style={{ color:T.textDim, fontFamily:FONT_MONO, padding:24 }}>Loading users…</div>;

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
      <Card title="Add User" subtitle="Create a new platform user">
        <form onSubmit={handleCreate} style={{ display:"flex", gap:10, flexWrap:"wrap", alignItems:"flex-end" }}>
          {[
            { label:"Email *",    key:"email",    placeholder:"ron@company.com", type:"email" },
            { label:"Name *",     key:"name",     placeholder:"Ron Haviv" },
            { label:"Password *", key:"password", placeholder:"min 8 chars", type:"password" },
            { label:"Team",       key:"team",     placeholder:"SOC" },
          ].map(({ label, key, placeholder, type }) => (
            <div key={key} style={{ display:"flex", flexDirection:"column", gap:4 }}>
              <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>{label}</label>
              <input type={type||"text"} placeholder={placeholder} value={form[key]}
                onChange={e => setForm({...form,[key]:e.target.value})}
                required={label.includes("*")}
                style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"6px 10px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, width:160 }}/>
            </div>
          ))}
          <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
            <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>Role</label>
            <select value={form.role} onChange={e => setForm({...form, role:e.target.value})}
              style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"6px 10px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, minWidth:120 }}>
              {Object.entries(roles).map(([r, m]) => <option key={r} value={r}>{m.label}</option>)}
            </select>
          </div>
          <button type="submit" disabled={saving}
            style={{ background:T.accent, color:T.bg, border:"none", padding:"8px 18px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, fontWeight:600, cursor:"pointer", opacity:saving?0.6:1 }}>
            {saving ? "Saving…" : "+ Add User"}
          </button>
        </form>
        {err && <div style={{ color:T.crit, fontFamily:FONT_MONO, fontSize:12, marginTop:10 }}>{err}</div>}
      </Card>

      <Card title="Platform Users" subtitle={`${users.length} user${users.length===1?"":"s"} registered — click Edit to change role or team`}>
        <SortableUsersTable users={users} currentUser={currentUser} editing={editing} editSaving={editSaving}
          setEditing={setEditing} saveEdit={saveEdit} cancelEdit={cancelEdit}
          handleToggle={handleToggle} handleDelete={handleDelete}
          onDisable={setDisableConfirm}
          inlineInput={inlineInput} inlineSelect={inlineSelect}
          onChangePassword={openPwModal} />
      </Card>

      {/* ── Change Password Modal ── */}
      {pwModal && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.6)", display:"flex", alignItems:"center", justifyContent:"center", zIndex:1000 }}>
          <div style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:8, padding:28, minWidth:340, display:"flex", flexDirection:"column", gap:16 }}>
            <div style={{ fontFamily:FONT_MONO, fontWeight:700, color:T.text, fontSize:14 }}>Change Password — {pwModal.name}</div>
            {[
              { label:"Current Password", val:pwOld,     set:setPwOld },
              { label:"New Password",     val:pwNew,     set:setPwNew },
              { label:"Confirm Password", val:pwConfirm, set:setPwConfirm },
            ].map(({ label, val, set }) => (
              <div key={label} style={{ display:"flex", flexDirection:"column", gap:4 }}>
                <label style={{ fontSize:9, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>{label}</label>
                <input type="password" value={val} onChange={e => set(e.target.value)} placeholder="min 8 characters"
                  style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"8px 12px", borderRadius:4, fontSize:13, fontFamily:FONT_MONO, width:"100%", boxSizing:"border-box" }} />
              </div>
            ))}
            {pwErr && <div style={{ color:T.crit, fontFamily:FONT_MONO, fontSize:12 }}>{pwErr}</div>}
            <div style={{ display:"flex", gap:10, justifyContent:"flex-end" }}>
              <button onClick={closePwModal} style={{ background:"transparent", color:T.textDim, border:`1px solid ${T.border}`, padding:"7px 16px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, cursor:"pointer" }}>
                Cancel
              </button>
              <button onClick={savePassword} disabled={pwSaving}
                style={{ background:T.accent, color:T.bg, border:"none", padding:"7px 18px", borderRadius:4, fontSize:12, fontFamily:FONT_MONO, fontWeight:600, cursor:"pointer", opacity:pwSaving?0.6:1 }}>
                {pwSaving ? "Saving…" : "Save Password"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Disable Confirmation Modal ── */}
      {disableConfirm && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.65)", display:"flex", alignItems:"center", justifyContent:"center", zIndex:1000 }}>
          <div style={{ background:T.panel, border:`1px solid ${T.warn}55`, borderRadius:10, padding:28, minWidth:340, maxWidth:420, display:"flex", flexDirection:"column", gap:18 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10 }}>
              <span style={{ fontSize:20, color:T.warn }}>⚠</span>
              <div style={{ fontWeight:700, color:T.text, fontSize:15 }}>Disable user?</div>
            </div>
            <div style={{ fontSize:13, color:T.textDim, lineHeight:1.6 }}>
              You are about to disable{" "}
              <strong style={{ color:T.text }}>{disableConfirm.name || disableConfirm.email}</strong>.
              {disableConfirm.id === currentUser?.id && (
                <span style={{ display:"block", marginTop:8, color:T.warn, fontWeight:600 }}>
                  Warning: this is your own account. You will be logged out immediately.
                </span>
              )}
            </div>
            <div style={{ display:"flex", gap:10, justifyContent:"flex-end" }}>
              <button onClick={() => setDisableConfirm(null)}
                style={{ background:"transparent", border:`1px solid ${T.border}`, color:T.textDim, padding:"7px 18px", borderRadius:5, fontSize:12, fontFamily:FONT_MONO, cursor:"pointer" }}>
                Cancel
              </button>
              <button onClick={() => { handleToggle(disableConfirm); setDisableConfirm(null); }}
                style={{ background:`${T.warn}18`, border:`1px solid ${T.warn}55`, color:T.warn, padding:"7px 18px", borderRadius:5, fontSize:12, fontFamily:FONT_MONO, cursor:"pointer", fontWeight:600 }}>
                Disable
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
