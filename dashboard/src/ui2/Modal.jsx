import { useEffect } from "react";
import { C, FONT, RADIUS } from "./tokens.js";

/**
 * ui2 Modal — centered dialog over a blurred night backdrop.
 *
 * Used by the intelligence pages to open an agent's detail as a popup:
 * click outside or press Escape to close. The aurora keyline across the
 * top carries the signature into the dialog. Body scroll is locked while
 * open; content scrolls inside the dialog.
 */
export default function Modal({ open, onClose, children, maxWidth = 780 }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 400,
        background: "rgba(2,4,12,0.72)",
        backdropFilter: "blur(5px)", WebkitBackdropFilter: "blur(5px)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
      }}>
      <div onClick={(e) => e.stopPropagation()} className="oa-rise" role="dialog" aria-modal="true"
        style={{
          position: "relative", width: "100%", maxWidth, maxHeight: "88vh",
          display: "flex", flexDirection: "column",
          background: C.surface, border: `1px solid ${C.borderStrong}`, borderRadius: RADIUS.lg,
          boxShadow: "0 1px 0 rgba(255,255,255,0.04) inset, 0 40px 110px rgba(0,0,0,0.72)",
          overflow: "hidden",
        }}>
        <div aria-hidden="true" style={{
          position: "absolute", top: 0, left: 24, right: 24, height: 2, zIndex: 1,
          background: "linear-gradient(90deg, transparent, #3BC7F0 25%, #7B8CFF 55%, #B07BFF 80%, transparent)",
          opacity: 0.9,
        }} />
        <button onClick={onClose} aria-label="Close"
          style={{
            position: "absolute", top: 14, right: 14, zIndex: 2,
            width: 32, height: 32, borderRadius: 9,
            background: C.surfaceRaised, border: `1px solid ${C.border}`, color: C.textDim,
            fontSize: 14, lineHeight: 1, cursor: "pointer", fontFamily: FONT.mono,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = C.text; e.currentTarget.style.borderColor = C.borderStrong; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = C.textDim; e.currentTarget.style.borderColor = C.border; }}>
          ✕
        </button>
        <div style={{ overflowY: "auto", padding: "24px 26px" }}>
          {children}
        </div>
      </div>
    </div>
  );
}
