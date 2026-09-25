import type { Metadata } from "next";
import { Hubble } from "@/components/lab/Hubble";
import { Intro } from "@/components/lab/Intro";

export const metadata: Metadata = {
  title: "Hubble diagram · Planet Hunter Lab",
  description: "Plot supernova brightness against redshift, draw a line through them and read off how fast the universe is expanding.",
};

export default function HubblePage() {
  return (
    <>
      <Intro title="Hubble diagram" data="demo">
        Exploding stars as distance markers. Draw a line through them and read off how fast the universe is expanding.
      </Intro>
      <Hubble />
    </>
  );
}
