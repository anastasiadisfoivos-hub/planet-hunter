import type { Metadata } from "next";
import { Suspense } from "react";
import { CandidateList } from "@/components/finder/CandidateList";
import l from "@/components/lab/lab.module.css";

export const metadata: Metadata = {
  title: "Finder · Planet Hunter",
  description: "Planet candidates from the nightly TESS search: signals that passed our checks and are not on the lists we checked. Review the evidence and vote.",
};

export default function FinderIndex() {
  return (
    <Suspense fallback={<div className={l.skeleton} role="status" aria-label="Loading candidates" />}>
      <CandidateList />
    </Suspense>
  );
}
