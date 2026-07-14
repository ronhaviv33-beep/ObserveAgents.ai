import React, { useState } from "react";
import { login as apiLogin, setToken } from "../api.js";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { BRAND } from "../config.js";
import { BrandMark } from "../ui2/AppShell.jsx";

const FONT_DISPLAY = "'Space Grotesk','Geist',-apple-system,'Segoe UI',sans-serif";

export default function LoginPage({ onLogin }) {
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [err,      setErr]      = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      const data = await apiLogin(email, password);
      setToken(data.access_token);
      onLogin(data.user, data.access_token);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position:"fixed", inset:0, background:T.bg, display:"flex", alignItems:"center", justifyContent:"center", zIndex:9999 }}>
      {/* aurora atmosphere */}
      <div aria-hidden="true" style={{
        position:"absolute", inset:0, pointerEvents:"none",
        background: [
          "radial-gradient(900px 480px at 20% -10%, rgba(59,199,240,0.10), transparent 60%)",
          "radial-gradient(800px 500px at 90% 110%, rgba(140,110,255,0.09), transparent 60%)",
          "radial-gradient(rgba(154,169,203,0.035) 1px, transparent 1.5px)",
        ].join(", "),
        backgroundSize: "auto, auto, 28px 28px",
      }} />
      <form onSubmit={submit} className="oa-rise" style={{
        position:"relative", background:T.panel, border:`1px solid ${T.border}`, borderRadius:16,
        boxShadow:"0 1px 0 rgba(255,255,255,0.04) inset, 0 24px 70px rgba(2,4,12,0.7)",
        padding:"40px 40px 36px", width:400, display:"flex", flexDirection:"column", gap:24,
      }}>
        {/* aurora keyline across the card top */}
        <div aria-hidden="true" style={{ position:"absolute", top:0, left:24, right:24, height:2,
          background:"linear-gradient(90deg, transparent, #3BC7F0 25%, #7B8CFF 55%, #B07BFF 80%, transparent)", opacity:0.85 }} />
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:14 }}>
            <BrandMark size={30} />
            <div>
              <div style={{ fontSize:17, fontWeight:600, letterSpacing:"-0.01em", color:T.text, fontFamily:FONT_DISPLAY }}>{BRAND.name}</div>
              <div style={{ fontSize:9, color:T.textMute, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", marginTop:2 }}>{BRAND.subtitle}</div>
            </div>
          </div>
          <div style={{ fontSize:13, color:T.textDim, lineHeight:1.6 }}>
            Sign in to see what your AI agents are actually doing.
          </div>
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
          {[
            { label:"Email", val:email, set:setEmail, type:"email",    placeholder:"you@company.com" },
            { label:"Password", val:password, set:setPassword, type:"password", placeholder:"••••••••" },
          ].map(({ label, val, set, type, placeholder }) => (
            <div key={label} style={{ display:"flex", flexDirection:"column", gap:6 }}>
              <label style={{ fontSize:9.5, fontFamily:FONT_MONO, letterSpacing:"0.12em", textTransform:"uppercase", color:T.textMute }}>{label}</label>
              <input type={type} value={val} onChange={e => set(e.target.value)} placeholder={placeholder} required
                style={{ background:T.panelHi, color:T.text, border:`1px solid ${T.border}`, padding:"10px 13px", borderRadius:8, fontSize:13, fontFamily:FONT_UI, outline:"none", transition:"border-color 0.15s" }}
                onFocus={(e) => { e.currentTarget.style.borderColor = T.accent; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = T.border; }} />
            </div>
          ))}
        </div>
        {err && <div style={{ fontSize:12, color:T.crit, fontFamily:FONT_MONO }}>{err}</div>}
        <button type="submit" disabled={loading}
          style={{ background:"linear-gradient(90deg, #3BC7F0, #56ADF5)", color:"#04121D", border:"none", padding:"12px 0",
            borderRadius:9, fontSize:13, fontFamily:FONT_UI, fontWeight:700, letterSpacing:"0.01em", cursor:"pointer",
            opacity:loading?0.6:1, boxShadow:"0 6px 20px rgba(59,199,240,0.25)" }}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
        <div style={{ fontSize:10.5, color:T.textMute, fontFamily:FONT_MONO, textAlign:"center", letterSpacing:"0.04em" }}>
          Observe first. Control only what matters.
        </div>
      </form>
    </div>
  );
}
