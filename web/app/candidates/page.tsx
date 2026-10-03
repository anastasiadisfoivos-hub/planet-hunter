import type { Metadata } from "next";
import { CandidateTable } from "@/components/finder/CandidateTable";
import { Site } from "@/components/shell/Site";

export const metadata: Metadata = {
  title: "Candidates · Planet Hunter",
  description: "Signals from the search that passed every check and are on no list of known objects: planet candidates, not confirmed planets.",
};

export default function CandidatesPage() {
  return (
    <Site>
      <CandidateTable />
    </Site>
  );
}
