// Centralized public URLs / branding for ObserveAgents.
// Values are overridable via Vite env vars; defaults point at the production
// custom domains. The Render fallback URL keeps working because nothing here
// changes how the API BASE is resolved (see api.js) or how CORS is enforced.

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
