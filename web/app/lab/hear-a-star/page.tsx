import type { Metadata } from "next";
import { HearStar } from "@/components/lab/HearStar";
import { Intro } from "@/components/lab/Intro";

export const metadata: Metadata = {
  title: "Hear a star · Planet Hunter Lab",
  description: "Listen to a real TESS light curve: brightness becomes pitch, and every planet transit is a drop in the tone.",
};

export default function HearAStarPage() {
  return (
    <>
      <Intro title="Hear a star" data="real">
        A real TESS recording of a star&apos;s brightness, turned into sound. When the planet crosses in front, the star dims and the note drops.
      </Intro>
      <HearStar />
    </>
  );
}
