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
import { Card, MonoLabel } from "../components/ui";

const STATS = [
  { label: "AI ASSETS DISCOVERED", value: 2, color: theme.text, sub: "0 managed" },
  { label: "OPEN FINDINGS", value: 27, color: theme.orange, sub: "across 2 agents" },
  { label: "ERROR TRACES", value: 4, color: theme.orange, sub: "5 slow traces" },
  {
    label: "GATEWAY CONTROL CANDIDATES",
    value: 2,
    color: theme.orange,
    sub: "recommended for review — nothing applied automatically",
  },
];

export const Beat1Stats: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TopCaption text="Runtime evidence, turned into findings." />
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 36,
          paddingTop: 120,
        }}
      >
        {STATS.map((stat, i) => {
          const delay = 8 + i * 10;
          const enter = spring({
            frame: frame - delay,
            fps,
            config: { damping: 16, stiffness: 120 },
          });
          const count = Math.round(
            interpolate(frame, [delay + 4, delay + 34], [0, stat.value], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            })
          );
          const landed = frame >= delay + 34;
          const pulse =
            stat.color === theme.orange && landed
              ? 1 +
                0.06 *
                  Math.max(
                    0,
                    Math.sin(((frame - delay - 34) / 14) * Math.PI) *
                      (frame - delay - 34 < 14 ? 1 : 0)
                  )
              : 1;
          return (
            <Card
              key={stat.label}
              style={{
                width: 380,
                height: 285,
                padding: "34px 38px",
                opacity: enter,
                transform: `translateY(${(1 - enter) * 60}px)`,
              }}
            >
              <MonoLabel text={stat.label} size={19} />
              <div
                style={{
                  fontFamily: theme.sans,
                  fontSize: 92,
                  fontWeight: 800,
                  color: stat.color,
                  lineHeight: 1.15,
                  transform: `scale(${pulse})`,
                  transformOrigin: "left center",
                }}
              >
                {count}
              </div>
              <div
                style={{
                  fontFamily: theme.mono,
                  fontSize: 19,
                  color: theme.textFaint,
                  lineHeight: 1.4,
                }}
              >
                {stat.sub}
              </div>
            </Card>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
