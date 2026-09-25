import type { Metadata } from "next";
import { Intro } from "@/components/lab/Intro";
import { Thermometer } from "@/components/lab/Thermometer";

export const metadata: Metadata = {
  title: "Star thermometer · Planet Hunter Lab",
  description: "Slide a star's temperature and watch its light shift from red to blue, then find real stars on the same scale.",
};

export default function ThermometerPage() {
  return (
    <>
      <Intro title="Star thermometer" data="real">
        A star&apos;s colour is a thermometer. Slide the temperature and watch where its light peaks, then find real stars from the sky map on the
        same scale.
      </Intro>
      <Thermometer />
    </>
  );
}
