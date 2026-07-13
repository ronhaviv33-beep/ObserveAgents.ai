import React from "react";
import { AbsoluteFill } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { theme } from "./theme";
import { Beat0Dashboard } from "./scenes/Beat0Dashboard";
import { Beat1Stats } from "./scenes/Beat1Stats";
import { Beat2TraceList } from "./scenes/Beat2TraceList";
import { Beat3Waterfall } from "./scenes/Beat3Waterfall";
import { Beat4Findings } from "./scenes/Beat4Findings";
import { Beat5GatewayCard } from "./scenes/Beat5GatewayCard";
import { Beat6Controls } from "./scenes/Beat6Controls";
import { EndCard } from "./scenes/EndCard";

const CROSSFADE = 15;

export const DURATIONS = {
  beat0: 175,
  beat1: 150,
  beat2: 145,
  beat3: 165,
  beat4: 150,
  beat5: 130,
  beat6: 175,
  end: 80,
};

export const TOTAL_DURATION =
  Object.values(DURATIONS).reduce((a, b) => a + b, 0) - CROSSFADE * 7;

export const OnboardingVideo: React.FC = () => {
  const transition = () => (
    <TransitionSeries.Transition
      presentation={fade()}
      timing={linearTiming({ durationInFrames: CROSSFADE })}
    />
  );

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={DURATIONS.beat0}>
          <Beat0Dashboard />
        </TransitionSeries.Sequence>
        {transition()}
        <TransitionSeries.Sequence durationInFrames={DURATIONS.beat1}>
          <Beat1Stats />
        </TransitionSeries.Sequence>
        {transition()}
        <TransitionSeries.Sequence durationInFrames={DURATIONS.beat2}>
          <Beat2TraceList />
        </TransitionSeries.Sequence>
        {transition()}
        <TransitionSeries.Sequence durationInFrames={DURATIONS.beat3}>
          <Beat3Waterfall />
        </TransitionSeries.Sequence>
        {transition()}
        <TransitionSeries.Sequence durationInFrames={DURATIONS.beat4}>
          <Beat4Findings />
        </TransitionSeries.Sequence>
        {transition()}
        <TransitionSeries.Sequence durationInFrames={DURATIONS.beat5}>
          <Beat5GatewayCard />
        </TransitionSeries.Sequence>
        {transition()}
        <TransitionSeries.Sequence durationInFrames={DURATIONS.beat6}>
          <Beat6Controls />
        </TransitionSeries.Sequence>
        {transition()}
        <TransitionSeries.Sequence durationInFrames={DURATIONS.end}>
          <EndCard />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
