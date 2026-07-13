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
import { Pointer } from "../components/Pointer";

const CARD_W = 900;
const CARD_X = (1920 - CARD_W) / 2;
const CARD_Y = 330;

// Button center in absolute canvas coordinates.
const BTN_X = CARD_X + 48 + 208;
const BTN_Y = CARD_Y + 200;

export const TAP_FRAME = 88;

export const Beat5GatewayCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame: frame - 6,
    fps,
    config: { damping: 16, stiffness: 110 },
  });

  const pressed = frame >= TAP_FRAME && frame <= TAP_FRAME + 10;

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TopCaption text="Control only what matters." />

      <div
        style={{
          position: "absolute",
          left: CARD_X - 60,
          top: CARD_Y - 66,
          opacity: enter * 0.9,
        }}
      >
        <MonoLabel text="GATEWAY CONTROL PREVIEW" size={20} />
      </div>

      <Card
        style={{
          position: "absolute",
          left: CARD_X,
          top: CARD_Y,
          width: CARD_W,
          padding: "42px 48px",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 70}px) scale(${
            0.96 + enter * 0.04
          })`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <span
            style={{
              fontFamily: theme.mono,
              fontSize: 30,
              fontWeight: 700,
              color: theme.text,
            }}
          >
            customer-support-agent
          </span>
          <HighBadge size={20} />
          <Chip text="production" size={20} border={theme.border} />
        </div>
        <div
          style={{
            fontFamily: theme.mono,
            fontSize: 22,
            color: theme.blue,
            marginTop: 26,
          }}
        >
          9 trigger findings · suggested: route through gateway
        </div>
        <div
          style={{
            marginTop: 40,
            display: "inline-block",
            fontFamily: theme.mono,
            fontSize: 22,
            fontWeight: 700,
            color: theme.orange,
            background: pressed ? theme.orangeSoft : theme.orangeFaint,
            border: `2px solid ${theme.orangeSoft}`,
            borderRadius: 10,
            padding: "16px 34px",
            transform: pressed ? "scale(0.96)" : "scale(1)",
          }}
        >
          Review in Control Center →
        </div>
      </Card>

      <div
        style={{
          position: "absolute",
          left: CARD_X,
          top: CARD_Y + 330,
          width: CARD_W,
          fontFamily: theme.sans,
          fontSize: 21,
          color: theme.textSoft,
          opacity: interpolate(frame, [30, 46], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        Recommendations only — no control is applied automatically.
      </div>

      <Pointer
        center={{ x: CARD_X + CARD_W / 2, y: CARD_Y + 170 }}
        stops={[{ x: BTN_X, y: BTN_Y, arrive: TAP_FRAME - 4, tapAt: TAP_FRAME }]}
        appearAt={52}
        fadeOutAt={TAP_FRAME + 20}
      />
    </AbsoluteFill>
  );
};
