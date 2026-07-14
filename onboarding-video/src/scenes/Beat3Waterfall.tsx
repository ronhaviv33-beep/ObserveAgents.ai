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
import { Card, Chip, MonoLabel } from "../components/ui";

const SPANS = [
  {
    name: "agent.workflow",
    sub: null,
    chip: { text: "Step", color: theme.textDim, bg: theme.surfaceRaised },
    bar: { width: 1, color: theme.textDim, height: 16 },
    ms: "200ms",
    indent: 0,
  },
  {
    name: "gen_ai.request",
    sub: "anthropic · claude-sonnet-5 · 850→300 tok",
    chip: { text: "LLM", color: theme.violet, bg: "rgba(142,123,255,0.14)" },
    bar: { width: 1, color: theme.violet, height: 16 },
    ms: "200ms",
    indent: 1,
  },
  {
    name: "db.query",
    sub: null,
    chip: { text: "Database", color: theme.riskLow, bg: "rgba(111,168,255,0.14)" },
    bar: { width: 0.04, color: theme.borderStrong, height: 10 },
    ms: "0ms",
    indent: 1,
  },
  {
    name: "mcp.call",
    sub: null,
    chip: { text: "MCP Tool", color: theme.riskHigh, bg: "rgba(255,138,76,0.14)" },
    bar: { width: 0.04, color: theme.borderStrong, height: 10 },
    ms: "0ms",
    indent: 1,
  },
];

const STATS = [
  { label: "TOTAL TIME", value: "200ms" },
  { label: "STEPS", value: "4" },
  { label: "ERRORS", value: "0", color: theme.ok },
  { label: "TOKENS IN / OUT", value: "850 / 300" },
];

const PANEL_W = 1560;
const PANEL_X = (1920 - PANEL_W) / 2;

export const Beat3Waterfall: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TopCaption text="See exactly where every run spent its time." />

      {/* Mini stat cards */}
      <div
        style={{
          position: "absolute",
          left: PANEL_X,
          top: 268,
          width: PANEL_W,
          display: "flex",
          gap: 24,
        }}
      >
        {STATS.map((stat, i) => {
          const enter = spring({
            frame: frame - (6 + i * 6),
            fps,
            config: { damping: 18, stiffness: 140 },
          });
          return (
            <Card
              key={stat.label}
              style={{
                flex: 1,
                padding: "22px 28px",
                opacity: enter,
                transform: `translateY(${(1 - enter) * 30}px)`,
              }}
            >
              <MonoLabel text={stat.label} size={17} />
              <div
                style={{
                  fontFamily: theme.display,
                  fontSize: 44,
                  fontWeight: 700,
                  color: stat.color ?? theme.text,
                  marginTop: 6,
                }}
              >
                {stat.value}
              </div>
            </Card>
          );
        })}
      </div>

      {/* Execution timeline */}
      <div
        style={{ position: "absolute", left: PANEL_X, top: 470, width: PANEL_W }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 18,
            opacity: interpolate(frame, [20, 32], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        >
          <MonoLabel text="EXECUTION TIMELINE" size={19} />
          <span
            style={{
              fontFamily: theme.mono,
              fontSize: 18,
              color: theme.textMute,
            }}
          >
            each step positioned by start offset, sized by duration
          </span>
        </div>
        <Card style={{ padding: "34px 40px" }}>
          {SPANS.map((span, i) => {
            const delay = 26 + i * 12;
            const enter = spring({
              frame: frame - delay,
              fps,
              config: { damping: 20, stiffness: 130 },
            });
            const grow = interpolate(
              frame,
              [delay + 8, delay + 46],
              [0, span.bar.width],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.out(Easing.cubic),
              }
            );
            return (
              <div
                key={span.name}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 20,
                  height: span.sub ? 92 : 76,
                  opacity: enter,
                  transform: `translateY(${(1 - enter) * 26}px)`,
                }}
              >
                <div style={{ width: 330, paddingLeft: span.indent * 36 }}>
                  <div
                    style={{
                      fontFamily: theme.mono,
                      fontSize: 23,
                      fontWeight: span.indent === 0 ? 700 : 500,
                      color: theme.text,
                    }}
                  >
                    {span.indent > 0 ? "⌞ " : ""}
                    {span.name}
                  </div>
                  {span.sub ? (
                    <div
                      style={{
                        fontFamily: theme.mono,
                        fontSize: 16.5,
                        color: theme.textMute,
                        marginTop: 5,
                        opacity: interpolate(
                          frame,
                          [delay + 24, delay + 36],
                          [0, 1],
                          {
                            extrapolateLeft: "clamp",
                            extrapolateRight: "clamp",
                          }
                        ),
                      }}
                    >
                      {span.sub}
                    </div>
                  ) : null}
                </div>
                <div style={{ width: 150 }}>
                  <Chip
                    text={span.chip.text}
                    color={span.chip.color}
                    bg={span.chip.bg}
                    size={18}
                  />
                </div>
                <div
                  style={{
                    flex: 1,
                    height: 22,
                    borderRadius: 999,
                    background: theme.surfaceRaised,
                    overflow: "hidden",
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  <div
                    style={{
                      width: `${grow * 100}%`,
                      height: span.bar.height,
                      minWidth: grow > 0 ? 8 : 0,
                      borderRadius: 999,
                      marginLeft: 3,
                      background: span.bar.color,
                      boxShadow:
                        span.indent === 1 && span.chip.text === "LLM"
                          ? `0 0 14px ${theme.violet}66`
                          : undefined,
                    }}
                  />
                </div>
                <span
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 20,
                    color: theme.textDim,
                    width: 90,
                    textAlign: "right",
                  }}
                >
                  {span.ms}
                </span>
              </div>
            );
          })}
        </Card>
      </div>
    </AbsoluteFill>
  );
};
