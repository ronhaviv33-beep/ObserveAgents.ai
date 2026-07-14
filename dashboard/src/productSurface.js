// Product surface mode — Observability vs Gateway split (see docs/architecture.md).
//
// ObserveAgents ships two customer-facing products on one shared backend:
//   observability — AI observability & intelligence through OpenTelemetry
//   gateway       — AI gateway, traffic control, budget & policy platform
//   combined      — today's blended surface (safe default when unset/unknown)
//
// The mode is a build-time Vite env var so a deployment renders exactly one
// product surface. Unset or unknown values ALWAYS fall back to "combined",
// which preserves current behavior byte-for-byte (every surface conditional
// in the app is false in combined mode).
//
// This gates the UI only. Role page-lists (backend) remain the access-control
// layer; API-level access is unchanged by surface (route/key scoping is
// Phase 4 of the separation plan).

const _raw = (import.meta.env.VITE_PRODUCT_SURFACE || "").trim().toLowerCase();

export const PRODUCT_SURFACE =
  _raw === "observability" || _raw === "gateway" ? _raw : "combined";

export const isObservability = PRODUCT_SURFACE === "observability";
export const isGateway       = PRODUCT_SURFACE === "gateway";
export const isCombined      = PRODUCT_SURFACE === "combined";

export const PRODUCT_LABEL = {
  observability: "ObserveAgents Observability",
  gateway:       "ObserveAgents Gateway",
  combined:      "ObserveAgents",
}[PRODUCT_SURFACE];

// Sidebar subtitle under the "ObserveAgents" wordmark.
export const PRODUCT_SUBTITLE = {
  observability: "Observability",
  gateway:       "AI Gateway",
  combined:      null, // combined keeps BRAND.subtitle
}[PRODUCT_SURFACE];

// Page ids hidden per surface. Hiding removes the page from nav AND makes
// deep links (#hash) fall back to the dashboard. Combined hides nothing.
// NOTE: "gateway_control_center" is deliberately absent from BOTH hidden sets —
// O9's one-app model: the Observe surface reaches Gateway Control with one
// click (docs/gateway_control_center_architecture.md), no env-var switch.
const _HIDDEN = {
  observability: new Set([
    // gateway product pages
    "discovery", "agent_inventory", "budgets", "pricing", "chat", "providers",
    // cost intelligence reads gateway telemetry only — hiding it here is the
    // honest choice until an OTel cost-signal aggregation exists (plan §9.8)
    "cost",
    // future/shared-later + legacy gateway-era pages
    "ecosystem", "home", "overview", "agents", "models", "workflows",
    "alerts", "assets", "onboarding",
  ]),
  gateway: new Set([
    // observability product pages
    "runtime", "intelligence", "guardrails", "relationship_map",
    "security_intel", "rules_alerts", "ecosystem",
    // the platform guide tells the observability story
    "welcome", "onboarding",
  ]),
  combined: new Set(),
};

export function surfaceAllowsPage(id) {
  return !_HIDDEN[PRODUCT_SURFACE].has(id);
}
