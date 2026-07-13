import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme, uiEase } from "../theme";

export const EndCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const logo = spring({
    frame: frame - 4,
    fps,
    config: { damping: 15, stiffness: 110 },
  });
  const tagline = interpolate(frame, [16, 32], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(...uiEase),
  });

  return (
    <AbsoluteFill
      style={{
        background: theme.bgTint,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 26,
          opacity: logo,
          transform: `translateY(${(1 - logo) * 50}px)`,
        }}
      >
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: "50%",
            background: theme.blue,
          }}
        />
        <div
          style={{
            fontFamily: theme.sans,
            fontSize: 96,
            fontWeight: 800,
            color: theme.text,
            letterSpacing: -2,
          }}
        >
          ObserveAgents<span style={{ color: theme.blue }}>.ai</span>
        </div>
      </div>
      <div
        style={{
          fontFamily: theme.mono,
          fontSize: 32,
          color: theme.textSoft,
          marginTop: 42,
          opacity: tagline,
          transform: `translateY(${(1 - tagline) * 60}px)`,
        }}
      >
        Observe first. <span style={{ color: theme.blue }}>Control only what matters.</span>
      </div>
    </AbsoluteFill>
  );
};
