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
        background: theme.bgVoid,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at 30% 30%, rgba(59,199,240,0.14), transparent 55%), radial-gradient(circle at 75% 65%, rgba(142,123,255,0.14), transparent 55%)",
        }}
      />
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
            width: 58,
            height: 58,
            borderRadius: 16,
            background: `linear-gradient(135deg, ${theme.accent}, ${theme.violet})`,
            boxShadow: `0 0 40px rgba(59,199,240,0.4)`,
            display: "grid",
            placeItems: "center",
          }}
        >
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: "50%",
              background: theme.bgVoid,
              boxShadow: "0 0 0 4px rgba(255,255,255,0.25)",
            }}
          />
        </div>
        <div
          style={{
            fontFamily: theme.display,
            fontSize: 96,
            fontWeight: 700,
            color: theme.text,
            letterSpacing: -2,
          }}
        >
          ObserveAgents
          <span style={{ color: theme.accent }}>.ai</span>
        </div>
      </div>
      <div
        style={{
          fontFamily: theme.mono,
          fontSize: 32,
          color: theme.textDim,
          marginTop: 42,
          opacity: tagline,
          transform: `translateY(${(1 - tagline) * 60}px)`,
        }}
      >
        Observe first.{" "}
        <span style={{ color: theme.accent }}>Control only what matters.</span>
      </div>
    </AbsoluteFill>
  );
};
