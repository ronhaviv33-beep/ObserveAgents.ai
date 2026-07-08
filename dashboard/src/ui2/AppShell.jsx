import { C, FONT } from "./tokens.js";
import Sidebar from "./Sidebar.jsx";
import Topbar from "./Topbar.jsx";

/**
 * ui2 AppShell — global chrome: font imports + resets, the fixed mobile top
 * bar with hamburger, the sidebar (drawer on mobile), and the main content
 * area with the desktop Topbar. All state stays in App.jsx.
 */
export default function AppShell({
  brand, groups, page, pageLabel, onNavigate,
  user, onLogout, status, demoToggle, onRefresh, orgSwitcher,
  topbarItems, viewingOrg,
  bp, sidebarOpen, setSidebarOpen,
  children,
}) {
  const mobilePad = bp.isMobile ? "68px 16px 24px" : bp.isTablet ? "72px 20px 24px" : "20px 28px";
  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text, fontFamily: FONT.ui, fontSize: 14, display: "flex", overflowX: "hidden", position: "relative" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
        * { box-sizing:border-box; }
        html, body { overflow-x:hidden; max-width:100vw; }
        ::-webkit-scrollbar { width:8px; height:8px; }
        ::-webkit-scrollbar-track { background:${C.bg}; }
        ::-webkit-scrollbar-thumb { background:${C.border}; border-radius:4px; }
        ::-webkit-scrollbar-thumb:hover { background:${C.borderStrong}; }
        select { appearance:none; background-image:url("data:image/svg+xml;utf8,<svg fill='%23CBD5E1' xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24'><polygon points='6,9 18,9 12,16'/></svg>"); background-repeat:no-repeat; background-position:right 8px center; padding-right:22px !important; }
        button:focus-visible, a:focus-visible, select:focus-visible, input:focus-visible, textarea:focus-visible { outline:2px solid ${C.accent}; outline-offset:2px; }
        @media (max-width:639px) {
          ::-webkit-scrollbar { width:4px; height:4px; }
        }
      `}</style>

      {/* Mobile/Tablet: fixed top bar */}
      {!bp.isDesktop && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, height: 52, background: C.surface, borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", padding: "0 16px", gap: 12, zIndex: 150, flexShrink: 0 }}>
          <button onClick={() => setSidebarOpen((o) => !o)} aria-label="Toggle navigation"
            style={{ background: "none", border: "none", color: C.text, cursor: "pointer", padding: 0, display: "flex", flexDirection: "column", gap: 4, minWidth: 44, minHeight: 44, justifyContent: "center", alignItems: "center" }}>
            <span style={{ display: "block", width: 18, height: 2, background: C.text, borderRadius: 1 }} />
            <span style={{ display: "block", width: 18, height: 2, background: C.text, borderRadius: 1 }} />
            <span style={{ display: "block", width: 18, height: 2, background: C.text, borderRadius: 1 }} />
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 20, height: 20, background: C.accent, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT.mono, fontWeight: 600, fontSize: 11, color: C.accentInk }}>◆</div>
            <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em" }}>{brand.name}</div>
          </div>
          <div style={{ marginLeft: "auto", fontSize: 10, color: C.textDim, fontFamily: FONT.mono, textTransform: "uppercase", letterSpacing: "0.1em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 160 }}>
            {pageLabel}
          </div>
        </div>
      )}

      {/* Mobile/Tablet: sidebar backdrop */}
      {!bp.isDesktop && sidebarOpen && (
        <div onClick={() => setSidebarOpen(false)}
          style={{ position: "fixed", top: 52, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.55)", zIndex: 190, touchAction: "none" }} />
      )}

      <Sidebar
        brand={brand} groups={groups} page={page}
        onNavigate={(id) => { onNavigate(id); if (!bp.isDesktop) setSidebarOpen(false); }}
        user={user} onLogout={onLogout} status={status} demoToggle={demoToggle}
        onRefresh={onRefresh} orgSwitcher={orgSwitcher}
        mobile={{ isDesktop: bp.isDesktop, open: sidebarOpen, onClose: () => setSidebarOpen(false) }} />

      <main style={{ flex: 1, padding: mobilePad, overflow: "auto", minWidth: 0 }}>
        {!bp.isMobile && (
          <Topbar pageId={page} pageLabel={pageLabel} isTablet={bp.isTablet}
            items={topbarItems} viewingOrg={viewingOrg} />
        )}
        {children}
      </main>
    </div>
  );
}
