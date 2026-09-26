import type { Metadata } from "next";
import { Sensitivity } from "@/components/finder/Sensitivity";

export const metadata: Metadata = {
  title: "What the search can find · Planet Hunter Finder",
  description: "Injection and recovery: simulated planets hidden in real TESS light curves, and how many of them the nightly search finds, by size and period.",
};

export default function SensitivityPage() {
  return <Sensitivity />;
}
