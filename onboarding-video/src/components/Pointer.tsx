import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { theme, uiEase } from "../theme";

export type PointerStop = {
  x: number;
  y: number;
  arrive: number; // frame at which the pointer reaches this stop
  tapAt: number; // frame at which the tap ripple fires
};

// Cursor that fades in at the visual center of the focal area, then glides
// in single straight segments from stop to stop, tapping at each one.
// It stays visible between taps on the same UI and fades out only after
// the last interaction.
export const Pointer: React.FC<{
  center: { x: number; y: number };
  stops: PointerStop[];
  appearAt: number;
  fadeOutAt: number;
}> = ({ center, stops, appearAt, fadeOutAt }) => {
  const frame = useCurrentFrame();
  const ease = Easing.bezier(...uiEase);

  const fadeIn = interpolate(frame, [appearAt, appearAt + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(frame, [fadeOutAt, fadeOutAt + 8], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = Math.min(fadeIn, fadeOut);
  if (opacity <= 0) return null;

  // Build straight segments: center -> stop 1 -> stop 2 -> ...
  const points = [
    { x: center.x, y: center.y, arrive: appearAt + 8 },
    ...stops,
  ];
  let x = points[0].x;
  let y = points[0].y;
  for (let i = 1; i < points.length; i++) {
    const from = points[i - 1];
    const to = points[i];
    const start = from.arrive + 4;
    const t = interpolate(frame, [start, to.arrive], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: ease,
    });
    x = x + (to.x - x) * t;
    y = y + (to.y - y) * t;
  }

  // Press-down scale on each tap.
  let scale = 1;
  for (const stop of stops) {
    const press = interpolate(
      frame,
      [stop.tapAt, stop.tapAt + 4, stop.tapAt + 10],
      [1, 0.82, 1],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );
    scale = Math.min(scale, press);
  }

  return (
    <>
      {stops.map((stop, i) => (
        <TapRipple key={i} x={stop.x} y={stop.y} at={stop.tapAt} />
      ))}
      <svg
        width={44}
        height={44}
        viewBox="0 0 24 24"
        style={{
          position: "absolute",
          left: x - 6,
          top: y - 4,
          opacity,
          transform: `scale(${scale})`,
          transformOrigin: "6px 4px",
          filter:
            "drop-shadow(0 2px 6px rgba(0,0,0,0.55)) drop-shadow(0 0 10px rgba(59,199,240,0.35))",
        }}
      >
        <path
          d="M5.5 2.5 L5.5 17.5 L9.3 13.9 L11.6 19.4 L14.4 18.2 L12.1 12.8 L17.3 12.5 Z"
          fill={theme.text}
          stroke={theme.bgVoid}
          strokeWidth={1.3}
        />
      </svg>
    </>
  );
};

const TapRipple: React.FC<{ x: number; y: number; at: number }> = ({
  x,
  y,
  at,
}) => {
  const frame = useCurrentFrame();
  if (frame < at) return null;
  const t = interpolate(frame, [at, at + 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });
  const size = 12 + t * 70;
  return (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        border: `3px solid rgba(59, 199, 240, ${0.6 * (1 - t) + 0.05})`,
        background: "rgba(59, 199, 240, 0.14)",
        opacity: 1 - t,
      }}
    />
  );
};
