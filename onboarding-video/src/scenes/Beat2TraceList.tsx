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
import { Card, Chip, Dot } from "../components/ui";
import { Pointer } from "../components/Pointer";

const ROWS = [
  {
    dot: theme.riskHigh,
    id: "23891659",
    time: "11:56:02 AM",
    steps: "8 steps",
    errors: "3 errors",
    ms: "0ms",
  },
  {
    dot: theme.accent,
    id: "ec34c8fa",
    time: "11:56:01 AM",
    steps: "4 steps",
    errors: null,
    ms: "200ms",
  },
  {
    dot: theme.riskHigh,
    id: "1d1d93f7",
    time: "11:55:05 AM",
    steps: "8 steps",
    errors: "3 errors",
    ms: "0ms",
  },
  {
    dot: theme.accent,
    id: "6e6d2144",
    time: "11:55:05 AM",
    steps: "4 steps",
    errors: null,
    ms: "200ms",
  },
];

const LIST_W = 1240;
const LIST_X = (1920 - LIST_W) / 2;
const LIST_Y = 300;
const HEADER_H = 96;
const ROW_H = 100;

// Center of the tapped row (index 1) in absolute canvas coordinates.
const TAP_X = LIST_X + LIST_W / 2 + 120;
const TAP_Y = LIST_Y + HEADER_H + ROW_H * 1.5 + 18;

export const TAP_FRAME = 100;

export const Beat2TraceList: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rowHighlight = interpolate(
    frame,
    [TAP_FRAME, TAP_FRAME + 6],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TopCaption text="Every agent run, traced." />
      <div
        style={{
          position: "absolute",
          left: LIST_X,
          top: LIST_Y,
          width: LIST_W,
        }}
      >
        {/* Group header row */}
        <GroupHeader frame={frame} fps={fps} />
        {/* Trace rows */}
        {ROWS.map((row, i) => {
          const delay = 18 + i * 8;
          const enter = spring({
            frame: frame - delay,
            fps,
            config: { damping: 18, stiffness: 140 },
          });
          const isTapped = i === 1;
          return (
            <div
              key={row.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 22,
                height: ROW_H,
                marginTop: 12,
                padding: "0 30px",
                borderRadius: theme.radiusMd,
                background: isTapped
                  ? `rgba(59, 199, 240, ${rowHighlight * 0.1})`
                  : "transparent",
                border: isTapped
                  ? `1.5px solid rgba(59, 199, 240, ${rowHighlight * 0.5})`
                  : "1.5px solid transparent",
                opacity: enter,
                transform: `translateY(${(1 - enter) * 40}px)`,
              }}
            >
              <Dot color={row.dot} />
              <div style={{ flex: 1 }}>
                <div
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 25,
                    fontWeight: 700,
                    color: theme.text,
                  }}
                >
                  agent.workflow
                </div>
                <div
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 19,
                    color: theme.textMute,
                    marginTop: 6,
                  }}
                >
                  customer-support-agent · Jul 13, {row.time} · # {row.id}
                </div>
              </div>
              <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                <Chip text={row.steps} />
                {row.errors ? (
                  <Chip
                    text={row.errors}
                    color={theme.riskHigh}
                    bg="rgba(255, 138, 76, 0.12)"
                    border="rgba(255, 138, 76, 0.35)"
                  />
                ) : null}
                <span
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 21,
                    fontWeight: 700,
                    color: theme.text,
                    minWidth: 90,
                    textAlign: "right",
                  }}
                >
                  {row.ms}
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <Pointer
        center={{ x: LIST_X + LIST_W / 2, y: LIST_Y + 240 }}
        stops={[{ x: TAP_X, y: TAP_Y, arrive: TAP_FRAME - 4, tapAt: TAP_FRAME }]}
        appearAt={62}
        fadeOutAt={TAP_FRAME + 22}
      />
    </AbsoluteFill>
  );
};

const GroupHeader: React.FC<{ frame: number; fps: number }> = ({
  frame,
  fps,
}) => {
  const enter = spring({
    frame: frame - 8,
    fps,
    config: { damping: 18, stiffness: 140 },
  });
  return (
    <Card
      style={{
        display: "flex",
        alignItems: "center",
        gap: 22,
        height: HEADER_H,
        padding: "0 30px",
        background: theme.surfaceRaised,
        opacity: enter,
        transform: `translateY(${(1 - enter) * 40}px)`,
      }}
    >
      <Dot color={theme.riskHigh} />
      <span
        style={{
          fontFamily: theme.mono,
          fontSize: 27,
          fontWeight: 700,
          color: theme.text,
        }}
      >
        customer-support-agent
      </span>
      <Chip text="8 traces" />
      <div style={{ flex: 1 }} />
      <span
        style={{ fontFamily: theme.mono, fontSize: 21, color: theme.textDim }}
      >
        48 steps
      </span>
      <Chip
        text="12 errors"
        color={theme.riskHigh}
        bg="rgba(255, 138, 76, 0.12)"
        border="rgba(255, 138, 76, 0.35)"
      />
      <span
        style={{
          fontFamily: theme.mono,
          fontSize: 21,
          fontWeight: 700,
          color: theme.text,
        }}
      >
        804ms
      </span>
    </Card>
  );
};
