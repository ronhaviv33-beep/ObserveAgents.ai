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
import { Card, Chip, MonoLabel } from "../components/ui";

const CONTROLS = [
  { label: "route through gateway", chip: "routing step", tone: "purple" },
  { label: "human review requirement", chip: "available now", tone: "blue" },
  { label: "mcp/tool usage policy", chip: "requires Gateway routing", tone: "orange" },
  { label: "rate limit", chip: "requires Gateway routing", tone: "orange" },
  { label: "provider allowlist", chip: "requires Gateway routing", tone: "orange" },
  { label: "block unknown provider", chip: "requires Gateway routing", tone: "orange" },
  { label: "alert-only rule", chip: "available now", tone: "blue" },
];

const tones: Record<string, { color: string; bg: string }> = {
  purple: { color: theme.purple, bg: theme.purpleSoft },
  blue: { color: theme.blue, bg: theme.blueSoft },
  orange: { color: theme.orange, bg: theme.orangeSoft },
};

const PANEL_W = 980;
const PANEL_X = (1920 - PANEL_W) / 2;

export const Beat6Controls: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      {/* Same caption text as Beat 5 — static continuation, no re-animation. */}
      <TopCaption text="Control only what matters." staticEntry />

      <Card
        style={{
          position: "absolute",
          left: PANEL_X,
          top: 262,
          width: PANEL_W,
          padding: "38px 52px",
          background: "#f7f5f1",
        }}
      >
        <MonoLabel text="SUGGESTED CONTROLS" size={20} />
        <div style={{ marginTop: 26 }}>
          {CONTROLS.map((control, i) => {
            const delay = 10 + i * 7;
            const enter = spring({
              frame: frame - delay,
              fps,
              config: { damping: 18, stiffness: 150 },
            });
            const tone = tones[control.tone];
            // Subtle pulse on the "available now" chips once everything landed.
            const pulse =
              control.tone === "blue"
                ? 1 +
                  0.05 *
                    Math.max(
                      0,
                      Math.sin(((frame - 80) / 20) * Math.PI) *
                        (frame > 80 && frame < 100 ? 1 : 0)
                    )
                : 1;
            return (
              <div
                key={control.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  height: 64,
                  opacity: enter,
                  transform: `translateY(${(1 - enter) * 34}px)`,
                }}
              >
                <span
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 24,
                    color: theme.text,
                  }}
                >
                  {control.label}
                </span>
                <span style={{ transform: `scale(${pulse})` }}>
                  <Chip
                    text={control.chip}
                    color={tone.color}
                    bg={tone.bg}
                    size={19}
                  />
                </span>
              </div>
            );
          })}
        </div>
        <div
          style={{
            fontFamily: theme.sans,
            fontSize: 20,
            color: theme.textSoft,
            marginTop: 26,
            lineHeight: 1.5,
            opacity: interpolate(frame, [66, 84], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        >
          Recommendations only — nothing is applied automatically. Hard controls
          work only if this agent's traffic is routed through the Gateway, after
          explicit approval.
        </div>
      </Card>
    </AbsoluteFill>
  );
};
