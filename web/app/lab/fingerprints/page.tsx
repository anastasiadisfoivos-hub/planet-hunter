import type { Metadata } from "next";
import { Fingerprints } from "@/components/lab/Fingerprints";
import { Intro } from "@/components/lab/Intro";

export const metadata: Metadata = {
  title: "Chemical fingerprints · Planet Hunter Lab",
  description: "Read what stars and planets are made of from the barcodes in their light.",
};

export default async function FingerprintsPage({ searchParams }: { searchParams: Promise<{ tic?: string }> }) {
  const tic = Number((await searchParams).tic);
  return (
    <>
      <Intro title="Chemical fingerprints" data="mixed">
        Split light into its colours and dark or bright lines appear. Each element makes its own pattern, so the lines tell us what a star, or a
        planet&apos;s air, is made of.
      </Intro>
      <Fingerprints initialTic={tic > 0 ? tic : null} />
    </>
  );
}
