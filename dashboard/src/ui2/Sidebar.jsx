import { C, FONT, RADIUS, microLabel } from "./tokens.js";

/**
 * ui2 Sidebar — workspace-grouped navigation plus the operational footer
 * (platform-admin org switcher, user badge, status, demo toggle, refresh).
 *
 * Purely presentational: every piece of state lives in App.jsx and arrives
 * as data + callbacks, so swapping the shell cannot change behavior.
 */

function NavItem({ item, active, onClick }) {
  return (
    <button onClick={onClick}
      style={{
        background: active ? C.surfaceRaised : "transparent", border: "none",
        color: active ? C.text : C.textDim, textAlign: "left", padding: "8px 10px",
        fontSize: 12, borderRadius: RADIUS.sm, cursor: "pointer", fontFamily: FONT.ui,
        display: "flex", alignItems: "center", gap: 10, width: "100%", minHeight: 44,
        borderLeft: active ? `2px solid ${C.accent}` : "2px solid transparent",
        transition: "all 0.1s",
      }}>
      {item.label}
      {item.badge != null && item.badge > 0 && (
        <span style={{ marginLeft: "auto", background: C.riskHigh, color: C.bg, fontSize: 10, fontFamily: FONT.mono, padding: "1px 6px", borderRadius: 8, fontWeight: 600 }}>
          {item.badge}
        </span>
      )}
    </button>
  );
}

export default function Sidebar({
  brand, groups, page, onNavigate,
  user, onLogout,
  status,            // { demoMode, eventsLabel, updatedLabel }
  demoToggle,        // { show, demoMode, onToggle } | null
  onRefresh,
  orgSwitcher,       // null | { value, options, onChange, showReload, onReload, showSeed, popping, clearing, onPopulate, onClear, result }
  mobile,            // { isDesktop, open, onClose }
}) {
  const { isDesktop, open, onClose } = mobile;
  return (
    <aside style={
      isDesktop
        ? { width: 232, background: C.surface, borderRight: `1px solid ${C.border}`, padding: "22px 16px", display: "flex", flexDirection: "column", flexShrink: 0 }
        : { position: "fixed", top: 52, left: 0, bottom: 0, width: "min(320px, 85vw)", background: C.surface, borderRight: `1px solid ${C.border}`, padding: "16px", display: "flex", flexDirection: "column", zIndex: 200, transition: "transform 0.25s ease", overflowY: "auto", transform: open ? "translateX(0)" : "translateX(-100%)" }
    }>
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: isDesktop ? 30 : 20, padding: "0 6px" }}>
        <div style={{ width: 22, height: 22, background: C.accent, borderRadius: 5, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT.mono, fontWeight: 600, fontSize: 12, color: C.accentInk }}>◆</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em", color: C.text }}>{brand.name}</div>
          <div style={{ fontSize: 9, color: C.textMute, fontFamily: FONT.mono, letterSpacing: "0.08em", textTransform: "uppercase", marginTop: 1 }}>{brand.subtitle}</div>
        </div>
        {!isDesktop && (
          <button onClick={onClose} aria-label="Close navigation"
            style={{ background: "none", border: "none", color: C.textMute, cursor: "pointer", fontSize: 18, lineHeight: 1, padding: 0, minWidth: 36, minHeight: 36, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            ✕
          </button>
        )}
      </div>

      {/* Nav */}
      <nav style={{ display: "flex", flexDirection: "column", flex: 1, overflowY: "auto" }}>
        {groups.map((group, gi) => (
          <div key={gi} style={{ marginBottom: group.label ? 6 : 8 }}>
            {group.label && (
              <div style={{ ...microLabel, fontSize: 8, letterSpacing: "0.18em", padding: "10px 10px 5px", fontWeight: 500 }}>
                {group.label}
              </div>
            )}
            {group.items.map((item) => (
              <NavItem key={item.id} item={item} active={page === item.id} onClick={() => onNavigate(item.id)} />
            ))}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div style={{ marginTop: "auto", padding: "12px 8px", display: "flex", flexDirection: "column", gap: 10 }}>
        {orgSwitcher && (
          <div style={{ background: C.surfaceRaised, border: `1px solid ${C.purple}`, borderRadius: RADIUS.sm, padding: "8px 10px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 5 }}>
              <div style={{ fontSize: 8, fontFamily: FONT.mono, color: C.purple, textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600 }}>
                ◆ Platform View
              </div>
              {orgSwitcher.showReload && (
                <button onClick={orgSwitcher.onReload} title="Reload organizations"
                  style={{ background: "transparent", border: "none", color: C.purple, fontSize: 11, cursor: "pointer", padding: "0 2px", lineHeight: 1 }}>↻</button>
              )}
            </div>
            <select value={orgSwitcher.value || ""} onChange={(e) => orgSwitcher.onChange(e.target.value || null)}
              style={{ width: "100%", background: C.surface, border: `1px solid ${C.border}`, color: C.text, padding: "4px 6px", borderRadius: 3, fontSize: 11, fontFamily: FONT.mono, cursor: "pointer" }}>
              <option value="">All / Platform</option>
              {orgSwitcher.options.length === 0
                ? <option disabled value="">loading orgs…</option>
                : orgSwitcher.options.map((o) => <option key={o.id} value={String(o.id)}>{o.name}</option>)}
            </select>
            {orgSwitcher.showSeed && (
              <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                <button onClick={orgSwitcher.onPopulate} disabled={orgSwitcher.popping || orgSwitcher.clearing}
                  title="Seed realistic enterprise data: 5 teams, 5 agents, 30 days of telemetry, 10 MCP relationships, budgets"
                  style={{ width: "100%", background: C.accent, color: C.accentInk, border: "none", padding: "5px 8px", borderRadius: 3, fontSize: 10, fontFamily: FONT.mono, fontWeight: 600, cursor: "pointer", opacity: (orgSwitcher.popping || orgSwitcher.clearing) ? 0.5 : 1, letterSpacing: "0.06em" }}>
                  {orgSwitcher.popping ? "Populating…" : "Populate Organization"}
                </button>
                <button onClick={orgSwitcher.onClear} disabled={orgSwitcher.popping || orgSwitcher.clearing}
                  title="Delete all demo data (is_demo=true). Real customer data is not affected."
                  style={{ width: "100%", background: "transparent", color: C.riskHigh, border: `1px solid ${C.riskHigh}44`, padding: "5px 8px", borderRadius: 3, fontSize: 10, fontFamily: FONT.mono, cursor: "pointer", opacity: (orgSwitcher.popping || orgSwitcher.clearing) ? 0.5 : 1, letterSpacing: "0.06em" }}>
                  {orgSwitcher.clearing ? "Clearing…" : "Clear Demo Data"}
                </button>
                {orgSwitcher.result && (
                  <div style={{ fontSize: 9, fontFamily: FONT.mono, color: orgSwitcher.result.ok ? C.accent : C.riskHigh, lineHeight: 1.4 }}>
                    {orgSwitcher.result.ok ? "✓ " : "✗ "}{orgSwitcher.result.msg}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {user && (
          <div style={{ background: C.surfaceRaised, border: `1px solid ${C.border}`, borderRadius: RADIUS.sm, padding: "8px 10px", display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: user.roleColor, flexShrink: 0 }} />
            <div style={{ flex: 1, overflow: "hidden" }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name}</div>
              <div style={{ fontSize: 9, fontFamily: FONT.mono, color: user.roleColor, textTransform: "uppercase", letterSpacing: "0.1em" }}>{user.roleLabel}</div>
            </div>
            <button title="Sign out" onClick={onLogout}
              style={{ background: "transparent", border: "none", color: C.textMute, fontSize: 12, cursor: "pointer", padding: "2px 4px", lineHeight: 1, fontFamily: FONT.mono }}>⏻</button>
          </div>
        )}

        <div style={{ fontSize: 10, color: C.textMute, fontFamily: FONT.mono, letterSpacing: "0.08em", lineHeight: 1.8 }}>
          {status.demoMode && <div style={{ color: C.riskMedium }}>● demo mode</div>}
          <span>{status.eventsLabel}</span>
          {status.updatedLabel && <div style={{ marginTop: 2 }}>{status.updatedLabel}</div>}
        </div>

        {demoToggle?.show && (
          <button onClick={demoToggle.onToggle} title={demoToggle.demoMode ? "Switch to live data" : "Switch to demo mode"}
            style={{ width: "100%", background: "transparent", border: `1px solid ${demoToggle.demoMode ? C.riskMedium : C.accent}66`, color: demoToggle.demoMode ? C.riskMedium : C.accent, padding: "6px 10px", borderRadius: 3, fontSize: 10, fontFamily: FONT.mono, cursor: "pointer", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            {demoToggle.demoMode ? "⇄ show live" : "⇄ show demo"}
          </button>
        )}
        <button onClick={onRefresh}
          style={{ width: "100%", background: "transparent", border: `1px solid ${C.border}`, color: C.textDim, padding: "6px 10px", borderRadius: 3, fontSize: 10, fontFamily: FONT.mono, cursor: "pointer", letterSpacing: "0.08em", textTransform: "uppercase" }}>
          ↻ Refresh
        </button>
      </div>
    </aside>
  );
}
