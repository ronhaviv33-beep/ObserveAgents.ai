// Central runtime configuration for the frontend.
//
// Two concerns:
//  1. Runtime mode — fetch the public /config endpoint once at boot and cache it.
//     Defaults are production / demo-off so that if the fetch ever fails we NEVER
//     accidentally render demo controls or auto-login in a real customer env.
//  2. Public URLs / branding — canonical hostnames and copy, overridable via Vite
//     env vars; defaults point at the production custom domains.
import { BASE } from "./api.js";

// ── Runtime mode (from backend /config) ───────────────────────────────────────
let _config = {
  app_env: "production",
  demo_mode: false,
  public_app_url: "",
  public_gateway_url: "",
  public_marketing_url: "",
};
let _loaded = false;

export async function loadConfig() {
  try {
    const r = await fetch(`${BASE}/config`, { headers: { "Content-Type": "application/json" } });
    if (r.ok) _config = await r.json();
  } catch {
    /* keep safe production defaults */
  }
  _loaded = true;
  return _config;
}

export function getConfig() { return _config; }
export function isDemoMode() { return !!_config.demo_mode; }
export function isDevelopment() { return _config.app_env === "development"; }
export function isConfigLoaded() { return _loaded; }

// ── Public URLs (build-time, overridable via Vite env vars) ───────────────────
const _clean = (v, fallback) => {
  const raw = (v || "").trim().replace(/\/+$/, "");
  return raw || fallback;
};

// Primary production app lives at the apex domain (observeagents.ai), NOT app.*.
export const PUBLIC_APP_URL     = _clean(import.meta.env.VITE_PUBLIC_APP_URL,     "https://observeagents.ai");
export const PUBLIC_GATEWAY_URL  = _clean(import.meta.env.VITE_PUBLIC_GATEWAY_URL, "https://gateway.observeagents.ai");
export const PUBLIC_DEMO_URL     = _clean(import.meta.env.VITE_PUBLIC_DEMO_URL,    "https://demo.observeagents.ai");
export const PUBLIC_API_URL      = _clean(import.meta.env.VITE_PUBLIC_API_URL,     "https://api.observeagents.ai");
export const RENDER_FALLBACK_URL = _clean(import.meta.env.VITE_RENDER_FALLBACK_URL, "https://ai-asset-app.onrender.com");

// ── Demo-safe values ─────────────────────────────────────────────────────────
// The public demo must never reveal production infrastructure. In demo mode the
// customer-facing snippets use these synthetic values instead of the production
// gateway/app URLs. All env-overridable; defaults are demo-safe.
export const DEMO_PUBLIC_APP_URL     = _clean(import.meta.env.VITE_DEMO_PUBLIC_APP_URL,     "https://demo.observeagents.ai");
export const DEMO_PUBLIC_GATEWAY_URL = _clean(import.meta.env.VITE_DEMO_PUBLIC_GATEWAY_URL, "https://gateway.demo.local");
export const DEMO_SNIPPET_URL        = _clean(import.meta.env.VITE_DEMO_SNIPPET_URL,        "https://demo.observeagents.ai");
export const DEMO_GATEWAY_KEY        = "demo_gateway_key";
export const DEMO_PROVIDER_NAMES     = ["OpenAI", "Anthropic"];
export const DEMO_ORGANIZATION       = "Acme AI (Demo)";

// Gateway base URL shown in copy-paste setup snippets. In demo mode return the
// synthetic demo host so the public demo exposes zero production infrastructure;
// otherwise the production gateway customers point base_url at. Default false
// keeps every production code path byte-identical.
export function gatewayBaseUrl(demoMode = false) {
  return demoMode ? DEMO_SNIPPET_URL : PUBLIC_GATEWAY_URL;
}

// ── Branding ────────────────────────────────────────────────────────────────
export const BRAND = {
  name:     "ObserveAgents",
  subtitle: "AI Runtime Intelligence Platform",
  tagline:  "Observe every agent. Map every dependency. Govern every interaction.",
  taglineLines: ["Observe every agent.", "Map every dependency.", "Govern every interaction."],
};
