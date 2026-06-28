// Central runtime-config helper for the frontend.
//
// Fetches the public /config endpoint once at boot and caches it. Defaults are
// production / demo-off so that if the fetch ever fails we NEVER accidentally
// render demo controls or auto-login in a real customer environment.
import { BASE } from "./api.js";

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
