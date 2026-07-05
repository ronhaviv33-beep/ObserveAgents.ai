// Providers — ObserveAgents Gateway surface.
// Thin page around the Provider Credentials (BYOK) section from Settings so
// the Gateway nav has a dedicated "Providers" home. Same data, same API.
import React from "react";
import { T, FONT_MONO } from "../theme.js";
import { ProviderCredentialsSection } from "./Settings.jsx";

export default function ProvidersPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 860 }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 500, color: T.text, letterSpacing: "-0.01em" }}>Providers</div>
        <div style={{ fontSize: 12, color: T.textDim, marginTop: 4 }}>
          Connect the AI providers your organization routes traffic through. The gateway uses these
          credentials to reach the provider — your applications keep using their existing provider
          SDKs, pointed at the Gateway base_url.
        </div>
      </div>
      <ProviderCredentialsSection />
      <div style={{ fontSize: 11, color: T.textMute, fontFamily: FONT_MONO }}>
        No credential configured for a provider? Requests to it return a clear
        provider_not_configured error instead of failing silently.
      </div>
    </div>
  );
}
