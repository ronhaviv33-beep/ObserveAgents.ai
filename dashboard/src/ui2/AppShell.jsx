import { C, FONT } from "./tokens.js";
import Sidebar from "./Sidebar.jsx";
import Topbar from "./Topbar.jsx";

/**
 * ui2 AppShell — global chrome: resets, the night-console atmosphere (two
 * faint aurora glows + a dot grid, fixed, non-interactive), the fixed mobile
 * top bar with hamburger, the sidebar (drawer on mobile), and the main
 * content area with the desktop Topbar. All state stays in App.jsx.
 */
export default function AppShell({
  brand, groups, page, pageLabel, onNavigate,
  user, onLogout, status, demoToggle, onRefresh, orgSwitcher,
  topbarItems, viewingOrg,
  bp, sidebarOpen, setSidebarOpen,
  children,
}) {
  // Desktop padding is mirrored by Topbar's full-bleed negative margins —
  // change both together.
  const mobilePad = bp.isMobile ? "68px 16px 24px" : bp.isTablet ? "72px 20px 24px" : "28px 36px";
  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text, fontFamily: FONT.ui, fontSize: 14, display: "flex", overflowX: "hidden", position: "relative" }}>
      <style>{`
        * { box-sizing:border-box; }
        html, body { overflow-x:hidden; max-width:100vw; }
        ::-webkit-scrollbar { width:9px; height:9px; }
        ::-webkit-scrollbar-track { background:transparent; }
        ::-webkit-scrollbar-thumb { background:${C.surfaceRaised}; border-radius:5px; border:2px solid ${C.bg}; }
        ::-webkit-scrollbar-thumb:hover { background:${C.borderStrong}; }
        select { appearance:none; background-image:url("data:image/svg+xml;utf8,<svg fill='%235E6D90' xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24'><polygon points='6,9 18,9 12,16'/></svg>"); background-repeat:no-repeat; background-position:right 8px center; padding-right:22px !important; }
        input, select, textarea { color-scheme: dark; }
        button:focus-visible, a:focus-visible, select:focus-visible, input:focus-visible, textarea:focus-visible { outline:2px solid ${C.accent}; outline-offset:2px; }
        @media (max-width:639px) {
          ::-webkit-scrollbar { width:4px; height:4px; }
        }
      `}</style>

      {/* Atmosphere: two faint aurora glows + dot grid. Fixed, behind everything. */}
      <div aria-hidden="true" style={{
        position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none",
        background: [
          "radial-gradient(1100px 520px at 12% -12%, rgba(59,199,240,0.075), transparent 60%)",
          "radial-gradient(1000px 560px at 105% 112%, rgba(140,110,255,0.065), transparent 60%)",
          "radial-gradient(rgba(154,169,203,0.033) 1px, transparent 1.5px)",
        ].join(", "),
        backgroundSize: "auto, auto, 28px 28px",
      }} />

      {/* Mobile/Tablet: fixed top bar */}
      {!bp.isDesktop && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, height: 52, background: "rgba(7,10,20,0.85)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", padding: "0 16px", gap: 12, zIndex: 150, flexShrink: 0 }}>
          <button onClick={() => setSidebarOpen((o) => !o)} aria-label="Toggle navigation"
            style={{ background: "none", border: "none", color: C.text, cursor: "pointer", padding: 0, display: "flex", flexDirection: "column", gap: 4, minWidth: 44, minHeight: 44, justifyContent: "center", alignItems: "center" }}>
            <span style={{ display: "block", width: 18, height: 2, background: C.text, borderRadius: 1 }} />
            <span style={{ display: "block", width: 18, height: 2, background: C.text, borderRadius: 1 }} />
            <span style={{ display: "block", width: 18, height: 2, background: C.text, borderRadius: 1 }} />
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <BrandMark size={20} />
            <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em", fontFamily: FONT.display }}>{brand.name}</div>
          </div>
          <div style={{ marginLeft: "auto", fontSize: 10, color: C.textDim, fontFamily: FONT.mono, textTransform: "uppercase", letterSpacing: "0.1em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 160 }}>
            {pageLabel}
          </div>
        </div>
      )}

      {/* Mobile/Tablet: sidebar backdrop */}
      {!bp.isDesktop && sidebarOpen && (
        <div onClick={() => setSidebarOpen(false)}
          style={{ position: "fixed", top: 52, left: 0, right: 0, bottom: 0, background: "rgba(2,4,12,0.6)", backdropFilter: "blur(2px)", WebkitBackdropFilter: "blur(2px)", zIndex: 190, touchAction: "none" }} />
      )}

      <Sidebar
        brand={brand} groups={groups} page={page}
        onNavigate={(id) => { onNavigate(id); if (!bp.isDesktop) setSidebarOpen(false); }}
        user={user} onLogout={onLogout} status={status} demoToggle={demoToggle}
        onRefresh={onRefresh} orgSwitcher={orgSwitcher}
        mobile={{ isDesktop: bp.isDesktop, open: sidebarOpen, onClose: () => setSidebarOpen(false) }} />

      <main style={{ flex: 1, padding: mobilePad, overflow: "auto", minWidth: 0, position: "relative", zIndex: 1 }}>
        {!bp.isMobile && (
          <Topbar pageId={page} pageLabel={pageLabel} isTablet={bp.isTablet}
            items={topbarItems} viewingOrg={viewingOrg} />
        )}
        {children}
      </main>
    </div>
  );
}

/** The aurora gem — brand mark shared by shell + sidebar + login. */
export function BrandMark({ size = 22 }) {
  return (
    <div aria-hidden="true" style={{
      width: size, height: size, borderRadius: size * 0.28, flexShrink: 0,
      background: "linear-gradient(135deg, #3BC7F0 0%, #7B8CFF 55%, #B07BFF 100%)",
      boxShadow: "0 0 12px rgba(59,199,240,0.45), 0 0 24px rgba(176,123,255,0.25)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      {/* the "evidence pulse" — a waveform notch cut in ink */}
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 24 24" fill="none">
        <path d="M3 13.5 H8 L10.5 6.5 L14 18 L16.5 11 H21" stroke="#04121D" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
