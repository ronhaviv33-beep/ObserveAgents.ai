import React from "react";
import { Composition } from "remotion";
import { OnboardingVideo, TOTAL_DURATION } from "./OnboardingVideo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="OnboardingVideo"
      component={OnboardingVideo}
      durationInFrames={TOTAL_DURATION}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
