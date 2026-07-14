import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { theme, uiEase } from "../theme";

// Single caption band anchored ~100px from the top, reused by every beat.
// Rises in from ~60px below with a strong UI ease-out within the first
// 12 frames of the beat and stays on screen for the whole sequence.
// staticEntry renders it instantly at rest for continuation beats that
// share the exact same caption text as the previous beat.
export const TopCaption: React.FC<{
  text: string;
  staticEntry?: boolean;
}> = ({ text, staticEntry }) => {
  const frame = useCurrentFrame();
  const progress = staticEntry
    ? 1
    : interpolate(frame, [0, 12], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.bezier(...uiEase),
      });

  return (
    <div
      style={{
        position: "absolute",
        top: 96,
        left: 0,
        width: "100%",
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          fontFamily: theme.display,
          fontSize: 58,
          fontWeight: 700,
          color: theme.text,
          maxWidth: 1400,
          textAlign: "center",
          letterSpacing: -0.5,
          opacity: progress,
          transform: `translateY(${(1 - progress) * 60}px)`,
          textShadow: "0 0 40px rgba(59, 199, 240, 0.18)",
        }}
      >
        {text}
      </div>
    </div>
  );
};
