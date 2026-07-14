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

// Full Overview dashboard rebuilt from the "night console / aurora signal"
// redesign: sidebar sliver, breadcrumb, evidence chain, stat counters,
// drawing line chart, filling donut, growing bars — everything cascading in.
const SIDEBAR_W = 300;
const PAGE_W = 1560;
const PAGE_H = 1160;

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

  const zoom = interpolate(frame, [0, 175], [1, 1.045], {
    extrapolateRight: "clamp",
  });
  const fit = 0.685;

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at 12% 8%, rgba(59,199,240,0.08), transparent 50%), radial-gradient(circle at 85% 5%, rgba(142,123,255,0.08), transparent 45%)",
        }}
      />
      <TopCaption text="Everything your agents do — one dashboard." />
      <Sidebar frame={frame} />
      <div
        style={{
          position: "absolute",
          top: 228,
          left: SIDEBAR_W * fit + (1920 - SIDEBAR_W * fit - PAGE_W * fit) / 2,
          width: PAGE_W,
          height: PAGE_H,
          transform: `scale(${fit * zoom})`,
          transformOrigin: "top left",
        }}
      >
        <Header frame={frame} />
        <EvidenceChain frame={frame} />
        <StatRow frame={frame} />
        <div style={{ display: "flex", gap: 24, marginTop: 24 }}>
          {/* Left column */}
          <div style={{ width: 1000 }}>
            <RuntimeActivity frame={frame} />
            <div style={{ display: "flex", gap: 24, marginTop: 24 }}>
              <SeverityDonut frame={frame} />
              <LatencyBars frame={frame} />
            </div>
            <EventsPerAgent frame={frame} />
          </div>
          {/* Right column */}
          <div style={{ width: 536 }}>
            <AttentionList frame={frame} />
            <GatewayPreview frame={frame} />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// Slim sidebar sliver — enough chrome to read as the real product without
// competing with the caption / content.
const NAV_OBSERVE = [
  "Runtime",
  "Asset Intelligence",
  "Telemetry Quality",
  "Security Intelligence",
  "Rules & Alerts",
];
const NAV_CONTROL = ["Gateway Control Center", "Guardrails", "Budgets"];

const Sidebar: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = interpolate(frame, [0, 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const W = SIDEBAR_W * 0.685;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width: W,
        height: 1080,
        background: theme.surface,
        borderRight: `1px solid ${theme.border}`,
        opacity: enter,
        padding: "26px 20px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 26,
            height: 26,
            borderRadius: 8,
            background: `linear-gradient(135deg, ${theme.accent}, ${theme.violet})`,
          }}
        />
        <div>
          <div
            style={{
              fontFamily: theme.display,
              fontSize: 15,
              fontWeight: 700,
              color: theme.text,
            }}
          >
            ObserveAgents
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: 30,
          fontFamily: theme.mono,
          fontSize: 10,
          letterSpacing: 1.5,
          color: theme.textMute,
        }}
      >
        OBSERVE
      </div>
      <div
        style={{
          marginTop: 6,
          display: "flex",
          flexDirection: "column",
          gap: 3,
        }}
      >
        {NAV_OBSERVE.map((item) => (
          <div
            key={item}
            style={{
              fontFamily: theme.sans,
              fontSize: 13,
              color: theme.textDim,
              padding: "7px 10px",
              borderRadius: 8,
            }}
          >
            {item}
          </div>
        ))}
      </div>

      <div
        style={{
          marginTop: 22,
          fontFamily: theme.mono,
          fontSize: 10,
          letterSpacing: 1.5,
          color: theme.textMute,
        }}
      >
        CONTROL
      </div>
      <div
        style={{
          marginTop: 6,
          display: "flex",
          flexDirection: "column",
          gap: 3,
        }}
      >
        {NAV_CONTROL.map((item) => (
          <div
            key={item}
            style={{
              fontFamily: theme.sans,
              fontSize: 13,
              color: theme.textDim,
              padding: "7px 10px",
              borderRadius: 8,
            }}
          >
            {item}
          </div>
        ))}
      </div>
    </div>
  );
};

const Header: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 2);
  return (
    <div style={riser(enter)}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <div
          style={{
            fontFamily: theme.mono,
            fontSize: 15,
            color: theme.textMute,
          }}
        >
          OBSERVEAGENTS <span style={{ color: theme.textDim }}>›</span>{" "}
          <span style={{ color: theme.text }}>Overview</span>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontFamily: theme.mono,
              fontSize: 14,
              color: theme.textDim,
            }}
          >
            <Dot color={theme.ok} size={7} /> live · next refresh 13s
          </span>
          <Chip text="sample data" size={14} border={theme.border} />
        </div>
      </div>
      <div
        style={{
          fontFamily: theme.mono,
          fontSize: 15,
          color: theme.accentDark,
          marginTop: 18,
          letterSpacing: 1,
        }}
      >
        MISSION CONTROL
      </div>
      <div
        style={{
          fontFamily: theme.display,
          fontSize: 42,
          fontWeight: 700,
          color: theme.text,
          marginTop: 6,
          letterSpacing: -1,
        }}
      >
        Overview
      </div>
      <div
        style={{
          fontFamily: theme.sans,
          fontSize: 19,
          color: theme.textDim,
          marginTop: 8,
          maxWidth: 1100,
        }}
      >
        Runtime evidence from your AI systems, turned into inventory,
        findings, and control recommendations.{" "}
        <span style={{ color: theme.accent }}>
          Observe first. Control only what matters.
        </span>
      </div>
    </div>
  );
};

const CHAIN = [
  { text: "OTel / OTLP" },
  { text: "Runtime" },
  { text: "Assets" },
  { text: "Security" },
  { text: "Rules" },
  { text: "Gateway Control", violet: true },
];

const EvidenceChain: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 12);
  return (
    <Card
      style={{
        marginTop: 26,
        padding: "22px 40px",
        background: theme.surface,
        ...riser(enter),
      }}
    >
      <MonoLabel text="THE EVIDENCE CHAIN — TELEMETRY IN, CONTROL OUT" size={13} />
      <div
        style={{
          display: "flex",
          alignItems: "center",
          marginTop: 22,
          position: "relative",
        }}
      >
        {CHAIN.map((node, i) => {
          const lit = clamp(frame, 20 + i * 5, 34 + i * 5);
          const color = node.violet ? theme.violet : theme.accent;
          return (
            <React.Fragment key={node.text}>
              {i > 0 ? (
                <div
                  style={{
                    flex: 1,
                    height: 1.5,
                    background: theme.border,
                    position: "relative",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      background: `linear-gradient(90deg, ${theme.accent}, ${theme.violet})`,
                      opacity: lit,
                    }}
                  />
                </div>
              ) : null}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 10,
                  flexShrink: 0,
                }}
              >
                <div
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: "50%",
                    border: `2.5px solid ${color}`,
                    background: theme.surface,
                    opacity: 0.3 + lit * 0.7,
                    boxShadow: `0 0 ${12 * lit}px ${color}99`,
                  }}
                />
                <span
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 15,
                    color: theme.textDim,
                    whiteSpace: "nowrap",
                  }}
                >
                  {node.text}
                </span>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </Card>
  );
};

const STATS = [
  { label: "AI ASSETS DISCOVERED", value: 2, color: theme.text, sub: "1 managed" },
  { label: "OPEN FINDINGS", value: 27, color: theme.riskMedium, sub: "across 2 agents" },
  { label: "ERROR TRACES", value: 4, color: theme.riskHigh, sub: "5 slow traces" },
  { label: "GATEWAY CONTROL CANDIDATES", value: 2, color: theme.ok, sub: "recommended for review" },
];

const StatRow: React.FC<{ frame: number }> = ({ frame }) => {
  return (
    <div style={{ display: "flex", gap: 24, marginTop: 24 }}>
      {STATS.map((stat, i) => {
        const enter = useEnter(frame, 30 + i * 5);
        const count = Math.round(
          clamp(frame, 34 + i * 5, 60 + i * 5, 0, stat.value)
        );
        return (
          <Card
            key={stat.label}
            style={{ flex: 1, padding: "20px 24px", height: 148, ...riser(enter) }}
          >
            <MonoLabel text={stat.label} size={14} />
            <div
              style={{
                fontFamily: theme.display,
                fontSize: 54,
                fontWeight: 700,
                color: stat.color,
                lineHeight: 1.2,
                letterSpacing: -1.5,
              }}
            >
              {count}
            </div>
            <div
              style={{ fontFamily: theme.mono, fontSize: 14, color: theme.textMute }}
            >
              {stat.sub}
            </div>
          </Card>
        );
      })}
    </div>
  );
};

// Runtime activity line chart: cyan trace count falls off then spikes,
// orange errors spike at the end. Drawn with a clip-path sweep.
const CHART_W = 920;
const CHART_H = 170;

const linePath = (points: [number, number][]) =>
  points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");

const BLUE_PTS: [number, number][] = [
  [0, 20], [60, 60], [120, 130], [200, 158], [300, 162], [420, 164],
  [540, 164], [660, 162], [740, 150], [800, 90], [860, 20], [920, 5],
];
const ORANGE_PTS: [number, number][] = [
  [0, 168], [200, 168], [420, 168], [640, 168], [760, 166], [820, 140],
  [880, 100], [920, 88],
];

const RuntimeActivity: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 46);
  const sweep = clamp(frame, 52, 102);
  const labels = ["Jul 5", "Jul 6", "Jul 7", "Jul 8", "Jul 9", "Jul 10", "Jul 11", "Jul 12", "Jul 13"];
  return (
    <Card style={{ padding: "22px 28px", marginTop: 0, ...riser(enter) }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <MonoLabel text="RUNTIME ACTIVITY" size={15} />
        <span style={{ fontFamily: theme.mono, fontSize: 14, color: theme.textMute }}>
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
              d={`${linePath(BLUE_PTS)} L ${CHART_W} ${CHART_H} L 0 ${CHART_H} Z`}
              fill="rgba(59, 199, 240, 0.1)"
            />
            <path
              d={linePath(BLUE_PTS)}
              fill="none"
              stroke={theme.accent}
              strokeWidth={3.5}
              style={{ filter: `drop-shadow(0 0 6px ${theme.accent}88)` }}
            />
            <path
              d={`${linePath(ORANGE_PTS)} L ${CHART_W} ${CHART_H} L 0 ${CHART_H} Z`}
              fill="rgba(255, 138, 76, 0.08)"
            />
            <path
              d={linePath(ORANGE_PTS)}
              fill="none"
              stroke={theme.riskHigh}
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
            color: theme.textMute,
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
  const enter = useEnter(frame, 66);
  const sweep = clamp(frame, 70, 110);
  const R = 62;
  const C = 2 * Math.PI * R;
  const segments = [
    { frac: 12 / 27, color: theme.riskHigh, label: "12 high" },
    { frac: 11 / 27, color: theme.riskMedium, label: "11 medium" },
    { frac: 4 / 27, color: theme.textMute, label: "4 info" },
  ];
  let offset = 0;
  return (
    <Card style={{ width: 460, padding: "22px 28px", ...riser(enter) }}>
      <MonoLabel text="FINDINGS BY SEVERITY" size={15} />
      <div style={{ display: "flex", alignItems: "center", gap: 30, marginTop: 12 }}>
        <div style={{ position: "relative", width: 170, height: 170 }}>
          <svg width={170} height={170} style={{ transform: "rotate(-90deg)" }}>
            <circle cx={85} cy={85} r={R} fill="none" stroke={theme.surfaceRaised} strokeWidth={26} />
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
            <span style={{ fontFamily: theme.display, fontSize: 38, fontWeight: 700, color: theme.text }}>
              {Math.round(sweep * 27)}
            </span>
            <span style={{ fontFamily: theme.mono, fontSize: 12, color: theme.textMute, letterSpacing: 1 }}>
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
                opacity: clamp(frame, 84 + i * 5, 94 + i * 5),
              }}
            >
              <Dot color={seg.color} size={9} />
              <span style={{ fontFamily: theme.mono, fontSize: 16, color: theme.textDim }}>
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
  { label: "<1s", value: 9, color: theme.accent },
  { label: "1-5s", value: 1, color: theme.accent },
  { label: "5-15s", value: 1, color: theme.riskMedium },
  { label: "15s+", value: 4, color: theme.riskHigh },
];

const LatencyBars: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 72);
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
          const grow = clamp(frame, 76 + i * 6, 102 + i * 6);
          return (
            <div key={bar.label} style={{ textAlign: "center", width: 70 }}>
              <div
                style={{
                  height: Math.max(6, (bar.value / 9) * (MAX_H - 26) * grow),
                  background: bar.color,
                  borderRadius: 6,
                  boxShadow: `0 0 10px ${bar.color}55`,
                }}
              />
              <div
                style={{
                  fontFamily: theme.mono,
                  fontSize: 14,
                  color: theme.textMute,
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
  const enter = useEnter(frame, 86);
  const rows = [
    { name: "customer-support-agent", frac: 1, color: theme.riskHigh, meta: "8 ev · 12 err · 101ms" },
    { name: "web-research-agent", frac: 0.55, color: theme.accent, meta: "7 ev · 44.2s" },
  ];
  return (
    <Card style={{ padding: "22px 28px", marginTop: 24, ...riser(enter) }}>
      <MonoLabel text="EVENTS PER AGENT" size={15} />
      <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 16 }}>
        {rows.map((row, i) => {
          const grow = clamp(frame, 92 + i * 8, 122 + i * 8);
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
                  background: theme.surfaceRaised,
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
                  color: theme.textMute,
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
  { dot: theme.riskCritical, title: "customer-support-agent", sub: "10 high findings · 4 error traces" },
  { dot: theme.riskHigh, title: "MCP tools in production", sub: "28 occurrences · 1 agent" },
  { dot: theme.riskHigh, title: "Unknown provider in production", sub: "1 agent outside the catalog" },
  { dot: theme.riskMedium, title: "Human review recommended", sub: "1 agent with a high-risk combination" },
];

const AttentionList: React.FC<{ frame: number }> = ({ frame }) => {
  const enter = useEnter(frame, 50);
  return (
    <div style={riser(enter)}>
      <MonoLabel text="ATTENTION · WORST FIRST" size={15} />
      <Card style={{ marginTop: 12, padding: "6px 0" }}>
        {ATTENTION.map((item, i) => {
          const rowIn = clamp(frame, 56 + i * 6, 68 + i * 6);
          return (
            <div
              key={item.title}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                padding: "16px 22px",
                borderBottom: i < ATTENTION.length - 1 ? `1px solid ${theme.border}` : "none",
                opacity: rowIn,
                transform: `translateY(${(1 - rowIn) * 16}px)`,
              }}
            >
              <Dot color={item.dot} size={10} />
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: theme.mono, fontSize: 17, fontWeight: 700, color: theme.text }}>
                  {item.title}
                </div>
                <div style={{ fontFamily: theme.mono, fontSize: 14, color: theme.textMute, marginTop: 4 }}>
                  {item.sub}
                </div>
              </div>
              <span style={{ fontFamily: theme.mono, fontSize: 16, color: theme.accent }}>→</span>
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
  const enter = useEnter(frame, 72);
  return (
    <div style={{ marginTop: 26, ...riser(enter) }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <MonoLabel text="GATEWAY CONTROL PREVIEW" size={15} />
        <Chip text="Control Center →" size={15} color={theme.textDim} bg={theme.surface} border={theme.border} />
      </div>
      {GATEWAY_CARDS.map((card, i) => {
        const cardIn = clamp(frame, 80 + i * 10, 94 + i * 10);
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
            <div style={{ fontFamily: theme.mono, fontSize: 14, color: theme.accent, marginTop: 10 }}>
              {card.line}
            </div>
            <div
              style={{
                display: "inline-block",
                marginTop: 12,
                fontFamily: theme.mono,
                fontSize: 14,
                fontWeight: 700,
                color: theme.violet,
                background: "rgba(142,123,255,0.12)",
                border: `1.5px solid rgba(142,123,255,0.35)`,
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
          color: theme.textDim,
          marginTop: 12,
          opacity: clamp(frame, 104, 118),
        }}
      >
        Recommendations only — no control is applied automatically.
      </div>
    </div>
  );
};
