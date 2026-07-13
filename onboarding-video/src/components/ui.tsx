import React from "react";
import { theme } from "../theme";

// Small pill/chip badge as seen across the dashboard.
export const Chip: React.FC<{
  text: string;
  color?: string;
  bg?: string;
  border?: string;
  size?: number;
}> = ({ text, color = theme.textSoft, bg = "#f4f2ee", border, size = 20 }) => (
  <span
    style={{
      fontFamily: theme.mono,
      fontSize: size,
      color,
      background: bg,
      border: `1.5px solid ${border ?? "transparent"}`,
      borderRadius: 999,
      padding: `${size * 0.28}px ${size * 0.75}px`,
      whiteSpace: "nowrap",
      display: "inline-block",
    }}
  >
    {text}
  </span>
);

export const HighBadge: React.FC<{ scale?: number; size?: number }> = ({
  scale = 1,
  size = 19,
}) => (
  <span
    style={{
      fontFamily: theme.mono,
      fontSize: size,
      fontWeight: 700,
      letterSpacing: 1,
      color: theme.orange,
      background: theme.orangeFaint,
      border: `1.5px solid ${theme.orangeSoft}`,
      borderRadius: 6,
      padding: `${size * 0.25}px ${size * 0.6}px`,
      display: "inline-block",
      transform: `scale(${scale})`,
    }}
  >
    HIGH
  </span>
);

export const Card: React.FC<{
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ style, children }) => (
  <div
    style={{
      background: theme.card,
      border: `1.5px solid ${theme.border}`,
      borderRadius: 12,
      boxShadow: "0 1px 3px rgba(17, 24, 39, 0.04)",
      ...style,
    }}
  >
    {children}
  </div>
);

export const MonoLabel: React.FC<{
  text: string;
  size?: number;
  color?: string;
  spacing?: number;
}> = ({ text, size = 20, color = theme.textSoft, spacing = 1.5 }) => (
  <div
    style={{
      fontFamily: theme.mono,
      fontSize: size,
      color,
      letterSpacing: spacing,
      textTransform: "uppercase",
    }}
  >
    {text}
  </div>
);

export const Dot: React.FC<{ color: string; size?: number }> = ({
  color,
  size = 12,
}) => (
  <span
    style={{
      width: size,
      height: size,
      borderRadius: "50%",
      background: color,
      display: "inline-block",
      flexShrink: 0,
    }}
  />
);
