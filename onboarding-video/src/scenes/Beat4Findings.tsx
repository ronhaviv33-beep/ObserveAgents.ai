import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";
import { TopCaption } from "../components/TopCaption";
import { Card, Chip, HighBadge, MonoLabel } from "../components/ui";

const FINDINGS = [
  {
    title: "Sensitive System Access",
    mult: null,
    chip: "sensitive_system_access",
    source: "otel_trace · 8h ago",
    desc: "This AI system has access to sensitive systems (CRM, source control, database, or messaging) alongside external provider access.",
  },
  {
    title: "Agent Has Database Access",
    mult: "×4",
    chip: "agent_has_database_access",
    source: "runtime_security · 8h ago",
    desc: "This AI agent reaches a database at runtime. Review whether it should access this database and document owner and policy.",
  },
  {
    title: "MCP Tool Used in Production",
    mult: "×28",
    chip: "agent_uses_mcp_tool_in_production",
    source: "runtime_security · 8h ago",
    desc: "This AI agent invokes MCP tools in a production environment. Review MCP server/tool approval and create a policy profile if needed.",
  },
];

const PANEL_W = 1360;
const PANEL_X = (1920 - PANEL_W) / 2;

export const Beat4Findings: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Faded strip of capability chips above, implying the asset context.
  const contextOpacity = interpolate(frame, [4, 20], [0, 0.4], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TopCaption text="Findings surface automatically — with evidence." />

      <div
        style={{
          position: "absolute",
          left: PANEL_X,
          top: 258,
          width: PANEL_W,
          display: "flex",
          gap: 14,
          opacity: contextOpacity,
          filter: "blur(1.5px)",
        }}
      >
        <Chip text="provider: Anthropic" color={theme.blue} bg={theme.blueFaint} />
        <Chip text="model: claude-sonnet-5" color={theme.blue} bg={theme.blueFaint} />
        <Chip text="database: postgresql" color={theme.orange} bg={theme.orangeFaint} />
        <Chip text="runtime: production" color={theme.teal} bg={theme.tealSoft} />
        <Chip text="mcp: jira_search" color={theme.orange} bg={theme.orangeFaint} />
        <Chip text="+3" />
      </div>

      <div
        style={{ position: "absolute", left: PANEL_X, top: 330, width: PANEL_W }}
      >
        <div
          style={{
            display: "flex",
            gap: 26,
            alignItems: "baseline",
            marginBottom: 22,
            opacity: interpolate(frame, [8, 20], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        >
          <MonoLabel text="FINDINGS (19 OPEN)" size={21} color={theme.text} />
          <MonoLabel text="SECURITY" size={18} />
        </div>

        {FINDINGS.map((finding, i) => {
          const delay = 16 + i * 14;
          const enter = spring({
            frame: frame - delay,
            fps,
            config: { damping: 17, stiffness: 130 },
          });
          const badgePop = spring({
            frame: frame - delay - 6,
            fps,
            config: { damping: 10, stiffness: 220 },
          });
          return (
            <Card
              key={finding.title}
              style={{
                padding: "26px 34px",
                marginBottom: 18,
                opacity: enter,
                transform: `translateY(${(1 - enter) * 50}px)`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
                <HighBadge scale={badgePop} />
                <span
                  style={{
                    fontFamily: theme.sans,
                    fontSize: 28,
                    fontWeight: 700,
                    color: theme.text,
                  }}
                >
                  {finding.title}
                </span>
                {finding.mult ? (
                  <span
                    style={{
                      fontFamily: theme.mono,
                      fontSize: 20,
                      color: theme.textSoft,
                    }}
                  >
                    {finding.mult}
                  </span>
                ) : null}
                <Chip text={finding.chip} size={17} />
                <div style={{ flex: 1 }} />
                <span
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 18,
                    color: theme.textFaint,
                  }}
                >
                  {finding.source}
                </span>
              </div>
              <div
                style={{
                  fontFamily: theme.sans,
                  fontSize: 21,
                  color: theme.textSoft,
                  marginTop: 14,
                  lineHeight: 1.45,
                }}
              >
                {finding.desc}
              </div>
            </Card>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
