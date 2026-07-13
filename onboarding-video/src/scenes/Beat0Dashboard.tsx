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
import { Card, Chip, HighBadge, MonoLabel, Dot } from "../components/ui";

// Full Overview dashboard rebuilt from the screenshot, everything cascading
// in: stat counters, drawing line chart, filling donut, growing bars.
// Design-space size (scaled to fit under the caption band).
const PAGE_W = 1520;
const PAGE_H = 1120;

const ease = Easing.out(Easing.cubic);

const clamp = (
  frame: number,
  from: number,
  to: number,
  a = 0,
  b = 1
): number =>
  interpolate(frame, [from, to], [a, b], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });

const useEnter = (frame: number, delay: number) => {
  const { fps } = useVideoConfig();
  return spring({
    frame: frame - delay,
    fps,
    config: { damping: 18, stiffness: 140 },
  });
};

const riser = (enter: number): React.CSSProperties => ({
  opacity: enter,
  transform: `translateY(${(1 - enter) * 30}px)`,
});

export const Beat0Dashboard: React.FC = () => {
  const frame = useCurrentFrame();

  // Subtle push-in over the whole beat.
  const zoom = interpolate(frame, [0, 170], [1, 1.05], {
    extrapolateRight: "clamp",
  });
  const fit = 0.72;

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TopCaption text="Everything your agents do — one dashboard." />
      <div
        style={{
          position: "absolute",
          top: 228,
          left: (1920 - PAGE_W) / 2,
          width: PAGE_W,
          height: PAGE_H,
          transform: `scale(${fit * zoom})`,
          transformOrigin: "top center",
        }}
      >
        <Header frame={frame} />
        <StatRow frame={frame} />
        <div style={{ display: "flex", gap: 24, marginTop: 24 }}>
          {/* Left column */}
          <div style={{ width: 980 }}>
            <RuntimeActivity frame={frame} />
            <div style={{ display: "flex", gap: 24, marginTop: 24 }}>
              <SeverityDonut frame={frame} />
              <LatencyBars frame={frame} />
            </div>
            <EventsPerAgent frame={frame} />
          </div>
          {/* Right column */}
          <div style={{ width: 516 }}>
            <AttentionList frame={frame} />
            <GatewayPreview frame={frame} />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const PIPELINE = [
  { text: "OTel / OTLP", dim: false },
  { text: "Runtime", dim: false },
  { text: "Assets", dim: false },
  { text: "Security", dim: false },
  { text: "Rules planned", dim: true },
  { text: "Gateway Control", dim: false },
];

const Header: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 2);
  return (
    <div style={riser(enter)}>
      <div
        style={{
          fontFamily: theme.sans,
          fontSize: 40,
          fontWeight: 800,
          color: theme.text,
        }}
      >
        Overview
      </div>
      <div
        style={{
          fontFamily: theme.sans,
          fontSize: 19,
          color: theme.textSoft,
          marginTop: 8,
        }}
      >
        Runtime evidence from your AI systems, turned into inventory, findings,
        and control recommendations.{" "}
        <span style={{ color: theme.blue }}>
          Observe first. Control only what matters.
        </span>
      </div>
      <div style={{ display: "flex", gap: 14, marginTop: 18, alignItems: "center" }}>
        {PIPELINE.map((step, i) => {
          const chipIn = clamp(frame, 8 + i * 4, 18 + i * 4);
          return (
            <React.Fragment key={step.text}>
              {i > 0 ? (
                <span
                  style={{
                    fontFamily: theme.mono,
                    color: theme.textFaint,
                    fontSize: 18,
                    opacity: chipIn,
                  }}
                >
                  →
                </span>
              ) : null}
              <span style={{ opacity: chipIn }}>
                <Chip
                  text={step.text}
                  size={17}
                  color={
                    step.dim
                      ? theme.textFaint
                      : i === 0
                      ? theme.orange
                      : theme.slate
                  }
                  bg={theme.card}
                  border={theme.border}
                />
              </span>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

const STATS = [
  { label: "AI ASSETS DISCOVERED", value: 2, color: theme.text, sub: "0 managed" },
  { label: "OPEN FINDINGS", value: 27, color: theme.orange, sub: "across 2 agents" },
  { label: "ERROR TRACES", value: 4, color: theme.orange, sub: "5 slow traces" },
  { label: "GATEWAY CONTROL CANDIDATES", value: 2, color: theme.orange, sub: "recommended for review" },
];

const StatRow: React.FC<{ frame: number }> = ({ frame }) => {
  return (
    <div style={{ display: "flex", gap: 24, marginTop: 26 }}>
      {STATS.map((stat, i) => {
        const enter = useEnter(frame, 14 + i * 5);
        const count = Math.round(
          clamp(frame, 18 + i * 5, 44 + i * 5, 0, stat.value)
        );
        return (
          <Card
            key={stat.label}
            style={{ flex: 1, padding: "20px 24px", height: 148, ...riser(enter) }}
          >
            <MonoLabel text={stat.label} size={14} />
            <div
              style={{
                fontFamily: theme.sans,
                fontSize: 54,
                fontWeight: 800,
                color: stat.color,
                lineHeight: 1.2,
              }}
            >
              {count}
            </div>
            <div
              style={{ fontFamily: theme.mono, fontSize: 14, color: theme.textFaint }}
            >
              {stat.sub}
            </div>
          </Card>
        );
      })}
    </div>
  );
};

// Runtime activity line chart: blue trace count falls off then spikes,
// orange errors spike at the end. Drawn with a clip-path sweep.
const CHART_W = 900;
const CHART_H = 170;

const linePath = (points: [number, number][]) =>
  points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");

const BLUE_PTS: [number, number][] = [
  [0, 20], [60, 60], [120, 130], [200, 158], [300, 162], [420, 164],
  [540, 164], [660, 162], [740, 150], [800, 90], [860, 20], [900, 5],
];
const ORANGE_PTS: [number, number][] = [
  [0, 168], [200, 168], [420, 168], [640, 168], [760, 166], [820, 140],
  [870, 100], [900, 88],
];

const RuntimeActivity: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 30);
  const sweep = clamp(frame, 36, 86);
  const labels = ["Jul 5", "Jul 6", "Jul 7", "Jul 8", "Jul 9", "Jul 10", "Jul 11", "Jul 12", "Jul 13"];
  return (
    <Card style={{ padding: "22px 28px", marginTop: 0, ...riser(enter) }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <MonoLabel text="RUNTIME ACTIVITY" size={15} />
        <span style={{ fontFamily: theme.mono, fontSize: 14, color: theme.textFaint }}>
          4 error · 5 slow
        </span>
      </div>
      <div style={{ position: "relative", marginTop: 14 }}>
        <svg width={CHART_W} height={CHART_H} style={{ display: "block" }}>
          {[0.25, 0.5, 0.75].map((t) => (
            <line
              key={t}
              x1={0}
              x2={CHART_W}
              y1={CHART_H * t}
              y2={CHART_H * t}
              stroke={theme.border}
              strokeDasharray="4 6"
            />
          ))}
          <defs>
            <clipPath id="sweep">
              <rect x={0} y={0} width={CHART_W * sweep} height={CHART_H} />
            </clipPath>
          </defs>
          <g clipPath="url(#sweep)">
            <path
              d={`${linePath(BLUE_PTS)} L 900 ${CHART_H} L 0 ${CHART_H} Z`}
              fill="rgba(37, 99, 235, 0.08)"
            />
            <path
              d={linePath(BLUE_PTS)}
              fill="none"
              stroke={theme.blue}
              strokeWidth={3.5}
            />
            <path
              d={`${linePath(ORANGE_PTS)} L 900 ${CHART_H} L 0 ${CHART_H} Z`}
              fill="rgba(234, 88, 12, 0.08)"
            />
            <path
              d={linePath(ORANGE_PTS)}
              fill="none"
              stroke={theme.orangeBright}
              strokeWidth={3}
            />
          </g>
        </svg>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 8,
            fontFamily: theme.mono,
            fontSize: 13,
            color: theme.textFaint,
          }}
        >
          {labels.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
      </div>
    </Card>
  );
};

// Findings-by-severity donut: 12 high / 11 medium / 4 info out of 27.
const SeverityDonut: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 52);
  const sweep = clamp(frame, 56, 96);
  const R = 62;
  const C = 2 * Math.PI * R;
  const segments = [
    { frac: 12 / 27, color: theme.orange, label: "12 high" },
    { frac: 11 / 27, color: "#f59e0b", label: "11 medium" },
    { frac: 4 / 27, color: "#9ca3af", label: "4 info" },
  ];
  let offset = 0;
  return (
    <Card style={{ width: 452, padding: "22px 28px", ...riser(enter) }}>
      <MonoLabel text="FINDINGS BY SEVERITY" size={15} />
      <div style={{ display: "flex", alignItems: "center", gap: 30, marginTop: 12 }}>
        <div style={{ position: "relative", width: 170, height: 170 }}>
          <svg width={170} height={170} style={{ transform: "rotate(-90deg)" }}>
            <circle cx={85} cy={85} r={R} fill="none" stroke="#eceae4" strokeWidth={26} />
            {segments.map((seg) => {
              const start = offset;
              offset += seg.frac;
              const visible = Math.max(0, Math.min(seg.frac, sweep - start));
              return (
                <circle
                  key={seg.label}
                  cx={85}
                  cy={85}
                  r={R}
                  fill="none"
                  stroke={seg.color}
                  strokeWidth={26}
                  strokeDasharray={`${visible * C} ${C}`}
                  strokeDashoffset={-start * C}
                />
              );
            })}
          </svg>
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <span style={{ fontFamily: theme.sans, fontSize: 38, fontWeight: 800, color: theme.text }}>
              {Math.round(sweep * 27)}
            </span>
            <span style={{ fontFamily: theme.mono, fontSize: 12, color: theme.textFaint, letterSpacing: 1 }}>
              OPEN
            </span>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {segments.map((seg, i) => (
            <div
              key={seg.label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                opacity: clamp(frame, 70 + i * 5, 80 + i * 5),
              }}
            >
              <Dot color={seg.color} size={9} />
              <span style={{ fontFamily: theme.mono, fontSize: 16, color: theme.textSoft }}>
                {seg.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
};

const LATENCY = [
  { label: "<1s", value: 9, color: theme.blue },
  { label: "1-5s", value: 1, color: theme.blue },
  { label: "5-15s", value: 1, color: "#f59e0b" },
  { label: "15s+", value: 4, color: theme.orangeBright },
];

const LatencyBars: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 58);
  const MAX_H = 150;
  return (
    <Card style={{ flex: 1, padding: "22px 28px", ...riser(enter) }}>
      <MonoLabel text="LATENCY DISTRIBUTION" size={15} />
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: 34,
          height: MAX_H,
          marginTop: 26,
          paddingLeft: 10,
        }}
      >
        {LATENCY.map((bar, i) => {
          const grow = clamp(frame, 62 + i * 6, 88 + i * 6);
          return (
            <div key={bar.label} style={{ textAlign: "center", width: 70 }}>
              <div
                style={{
                  height: Math.max(6, (bar.value / 9) * (MAX_H - 26) * grow),
                  background: bar.color,
                  borderRadius: 6,
                }}
              />
              <div
                style={{
                  fontFamily: theme.mono,
                  fontSize: 14,
                  color: theme.textFaint,
                  marginTop: 8,
                }}
              >
                {bar.label}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

const EventsPerAgent: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 72);
  const rows = [
    { name: "customer-support-agent", frac: 1, color: theme.orangeBright, meta: "8 ev · 12 err · 101ms" },
    { name: "web-research-agent", frac: 0.55, color: theme.blue, meta: "7 ev · 44.2s" },
  ];
  return (
    <Card style={{ padding: "22px 28px", marginTop: 24, ...riser(enter) }}>
      <MonoLabel text="EVENTS PER AGENT" size={15} />
      <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 16 }}>
        {rows.map((row, i) => {
          const grow = clamp(frame, 78 + i * 8, 108 + i * 8);
          return (
            <div key={row.name} style={{ display: "flex", alignItems: "center", gap: 18 }}>
              <span
                style={{
                  fontFamily: theme.mono,
                  fontSize: 16,
                  color: theme.text,
                  width: 250,
                }}
              >
                {row.name}
              </span>
              <div
                style={{
                  flex: 1,
                  height: 18,
                  background: "#eceae4",
                  borderRadius: 999,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${row.frac * grow * 100}%`,
                    height: "100%",
                    borderRadius: 999,
                    background: row.color,
                  }}
                />
              </div>
              <span
                style={{
                  fontFamily: theme.mono,
                  fontSize: 13,
                  color: theme.textFaint,
                  width: 170,
                  textAlign: "right",
                }}
              >
                {row.meta}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

const ATTENTION = [
  { dot: "#dc2626", title: "customer-support-agent", sub: "10 high findings · 4 error traces" },
  { dot: theme.orangeBright, title: "MCP tools in production", sub: "28 occurrences · 1 agent" },
  { dot: theme.orangeBright, title: "Unknown provider in production", sub: "1 agent outside the catalog" },
  { dot: "#f59e0b", title: "Human review recommended", sub: "1 agent with a high-risk combination" },
];

const AttentionList: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 34);
  return (
    <div style={riser(enter)}>
      <MonoLabel text="ATTENTION · WORST FIRST" size={15} />
      <Card style={{ marginTop: 12, padding: "6px 0" }}>
        {ATTENTION.map((item, i) => {
          const rowIn = clamp(frame, 40 + i * 6, 52 + i * 6);
          return (
            <div
              key={item.title}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                padding: "16px 22px",
                borderBottom: i < ATTENTION.length - 1 ? `1px solid ${theme.borderSoft}` : "none",
                opacity: rowIn,
                transform: `translateY(${(1 - rowIn) * 16}px)`,
              }}
            >
              <Dot color={item.dot} size={10} />
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: theme.mono, fontSize: 17, fontWeight: 700, color: theme.text }}>
                  {item.title}
                </div>
                <div style={{ fontFamily: theme.mono, fontSize: 14, color: theme.textFaint, marginTop: 4 }}>
                  {item.sub}
                </div>
              </div>
              <span style={{ fontFamily: theme.mono, fontSize: 16, color: theme.blue }}>→</span>
            </div>
          );
        })}
      </Card>
    </div>
  );
};

const GATEWAY_CARDS = [
  {
    name: "web-research-agent",
    envChip: "unknown",
    line: "1 trigger finding · suggested: human review requirement",
  },
  {
    name: "customer-support-agent",
    envChip: "production",
    line: "9 trigger findings · suggested: route through gateway",
  },
];

const GatewayPreview: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 56);
  return (
    <div style={{ marginTop: 26, ...riser(enter) }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <MonoLabel text="GATEWAY CONTROL PREVIEW" size={15} />
        <Chip text="Control Center →" size={15} color={theme.slate} bg={theme.card} border={theme.border} />
      </div>
      {GATEWAY_CARDS.map((card, i) => {
        const cardIn = clamp(frame, 64 + i * 10, 78 + i * 10);
        return (
          <Card
            key={card.name}
            style={{
              marginTop: 14,
              padding: "18px 22px",
              opacity: cardIn,
              transform: `translateY(${(1 - cardIn) * 24}px)`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontFamily: theme.mono, fontSize: 18, fontWeight: 700, color: theme.text }}>
                {card.name}
              </span>
              <HighBadge size={13} />
              <Chip text={card.envChip} size={13} border={theme.border} />
            </div>
            <div style={{ fontFamily: theme.mono, fontSize: 14, color: theme.blue, marginTop: 10 }}>
              {card.line}
            </div>
            <div
              style={{
                display: "inline-block",
                marginTop: 12,
                fontFamily: theme.mono,
                fontSize: 14,
                fontWeight: 700,
                color: theme.orange,
                background: theme.orangeFaint,
                border: `1.5px solid ${theme.orangeSoft}`,
                borderRadius: 8,
                padding: "8px 16px",
              }}
            >
              Review in Control Center →
            </div>
          </Card>
        );
      })}
      <div
        style={{
          fontFamily: theme.sans,
          fontSize: 15,
          color: theme.textSoft,
          marginTop: 12,
          opacity: clamp(frame, 90, 104),
        }}
      >
        Recommendations only — no control is applied automatically.
      </div>
    </div>
  );
};
