import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";
import { TopCaption } from "../components/TopCaption";
import { Card, Chip, HighBadge, MonoLabel } from "../components/ui";

// Full expanded customer-support-agent card from the Gateway Control Center:
// header chips, "why this agent is here" evidence column, suggested controls.
const CARD_W = 1560;
const CARD_X = (1920 - CARD_W) / 2;
const CARD_Y = 240;

const ease = Easing.out(Easing.cubic);
const clamp = (frame: number, from: number, to: number) =>
  interpolate(frame, [from, to], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });

const HEADER_CHIPS: { text: string; color: string; bg: string }[] = [
  { text: "production", color: theme.textDim, bg: theme.surfaceRaised },
  { text: "9 findings", color: theme.textDim, bg: theme.surfaceRaised },
  { text: "routing required", color: theme.violet, bg: "rgba(142,123,255,0.14)" },
  { text: "recommended", color: theme.riskHigh, bg: "rgba(255,138,76,0.12)" },
];

const DETECTION_RULES = [
  "rule_mcp_tool_access_threshold",
  "rule_repeated_tool_errors",
  "rule_unknown_provider_in_production",
];
const SECURITY_INTEL = [
  "agent_has_database_access",
  "agent_uses_mcp_tool_in_production",
  "agent_uses_unknown_model_provider",
  "human_review_recommended",
  "repeated_tool_errors",
];
const ASSET_INTEL = ["sensitive_system_access"];

const CONTROLS = [
  { label: "route through gateway", chip: "routing step", tone: "violet" },
  { label: "human review requirement", chip: "available now", tone: "accent" },
  { label: "mcp/tool usage policy", chip: "requires Gateway routing", tone: "high" },
  { label: "rate limit", chip: "requires Gateway routing", tone: "high" },
  { label: "provider allowlist", chip: "requires Gateway routing", tone: "high" },
  { label: "block unknown provider", chip: "requires Gateway routing", tone: "high" },
  { label: "alert-only rule", chip: "available now", tone: "accent" },
];

const tones: Record<string, { color: string; bg: string }> = {
  violet: { color: theme.violet, bg: "rgba(142,123,255,0.14)" },
  accent: { color: theme.accent, bg: theme.accentSoft },
  high: { color: theme.riskHigh, bg: "rgba(255,138,76,0.12)" },
};

const ChipGroup: React.FC<{
  frame: number;
  delay: number;
  label: string;
  chips: string[];
}> = ({ frame, delay, label, chips }) => (
  <div style={{ marginTop: 26, opacity: clamp(frame, delay, delay + 12) }}>
    <MonoLabel text={label} size={15} />
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 10 }}>
      {chips.map((chip, i) => (
        <span
          key={chip}
          style={{ opacity: clamp(frame, delay + 4 + i * 3, delay + 12 + i * 3) }}
        >
          <Chip
            text={chip}
            size={15}
            color={theme.riskHigh}
            bg="rgba(255,138,76,0.1)"
            border="rgba(255,138,76,0.3)"
          />
        </span>
      ))}
    </div>
  </div>
);

export const Beat6Controls: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame: frame - 4,
    fps,
    config: { damping: 17, stiffness: 110 },
  });

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      {/* Same caption text as Beat 5 — static continuation, no re-animation. */}
      <TopCaption text="Control only what matters." staticEntry />

      <Card
        style={{
          position: "absolute",
          left: CARD_X,
          top: CARD_Y,
          width: CARD_W,
          overflow: "hidden",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 60}px)`,
        }}
      >
        {/* Card header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            padding: "26px 40px",
          }}
        >
          <div>
            <div
              style={{
                fontFamily: theme.mono,
                fontSize: 27,
                fontWeight: 700,
                color: theme.text,
              }}
            >
              customer-support-agent
            </div>
            <div
              style={{
                fontFamily: theme.mono,
                fontSize: 16,
                color: theme.textMute,
                marginTop: 6,
              }}
            >
              667b2eef17cb9140…
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <span style={{ opacity: clamp(frame, 12, 20) }}>
            <HighBadge size={16} />
          </span>
          {HEADER_CHIPS.map((chip, i) => (
            <span
              key={chip.text}
              style={{ opacity: clamp(frame, 15 + i * 3, 23 + i * 3) }}
            >
              <Chip text={chip.text} size={16} color={chip.color} bg={chip.bg} />
            </span>
          ))}
          <span
            style={{
              fontFamily: theme.mono,
              fontSize: 16,
              color: theme.textMute,
              opacity: clamp(frame, 27, 35),
            }}
          >
            8h ago
          </span>
        </div>

        {/* Card body — raised surface, two columns */}
        <div
          style={{
            background: theme.surfaceRaised,
            borderTop: `1px solid ${theme.border}`,
            display: "flex",
            gap: 56,
            padding: "30px 40px 36px",
          }}
        >
          {/* Left: why this agent is here */}
          <div style={{ width: 700 }}>
            <div style={{ opacity: clamp(frame, 16, 30) }}>
              <MonoLabel text="WHY THIS AGENT IS HERE" size={15} />
              <div
                style={{
                  fontFamily: theme.sans,
                  fontSize: 18.5,
                  color: theme.textDim,
                  lineHeight: 1.55,
                  marginTop: 12,
                }}
              >
                <span style={{ color: theme.accent }}>Runtime evidence</span>{" "}
                recommends reviewing this agent for Gateway control:{" "}
                <span style={{ color: theme.riskHigh }}>
                  9 open high-severity findings
                </span>{" "}
                and human review recommended (agent_has_database_access,
                agent_uses_mcp_tool_in_production,
                agent_uses_unknown_model_provider, human_review_recommended,
                repeated_tool_errors, rule_mcp_tool_access_threshold,
                rule_repeated_tool_errors, rule_unknown_provider_in_production,
                sensitive_system_access).
              </div>
            </div>
            <ChipGroup
              frame={frame}
              delay={34}
              label="DETECTION RULES"
              chips={DETECTION_RULES}
            />
            <ChipGroup
              frame={frame}
              delay={48}
              label="SECURITY INTELLIGENCE"
              chips={SECURITY_INTEL}
            />
            <ChipGroup
              frame={frame}
              delay={64}
              label="ASSET INTELLIGENCE"
              chips={ASSET_INTEL}
            />
          </div>

          {/* Right: suggested controls */}
          <div style={{ flex: 1 }}>
            <div style={{ opacity: clamp(frame, 20, 32) }}>
              <MonoLabel text="SUGGESTED CONTROLS" size={15} />
            </div>
            <div style={{ marginTop: 14 }}>
              {CONTROLS.map((control, i) => {
                const delay = 24 + i * 6;
                const rowIn = spring({
                  frame: frame - delay,
                  fps,
                  config: { damping: 18, stiffness: 150 },
                });
                const tone = tones[control.tone];
                return (
                  <div
                    key={control.label}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 16,
                      height: 47,
                      opacity: rowIn,
                      transform: `translateY(${(1 - rowIn) * 26}px)`,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: theme.sans,
                        fontSize: 19,
                        color: theme.text,
                      }}
                    >
                      {control.label}
                    </span>
                    <Chip
                      text={control.chip}
                      color={tone.color}
                      bg={tone.bg}
                      size={15}
                    />
                  </div>
                );
              })}
            </div>
            <div
              style={{
                fontFamily: theme.sans,
                fontSize: 16.5,
                color: theme.textDim,
                lineHeight: 1.5,
                marginTop: 18,
                maxWidth: 640,
                opacity: clamp(frame, 76, 92),
              }}
            >
              Recommendations only — nothing is applied automatically. Hard
              controls work only if this agent's traffic is routed through the
              Gateway, after explicit approval.
            </div>
            <div
              style={{
                display: "inline-block",
                marginTop: 20,
                fontFamily: theme.mono,
                fontSize: 17,
                color: theme.riskHigh,
                background: theme.surface,
                border: `1.5px solid rgba(255,138,76,0.3)`,
                borderRadius: 8,
                padding: "10px 22px",
                opacity: clamp(frame, 86, 100),
              }}
            >
              Dismiss recommendation
            </div>
          </div>
        </div>
      </Card>
    </AbsoluteFill>
  );
};
