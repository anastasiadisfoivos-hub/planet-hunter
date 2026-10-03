import type { Metadata } from "next";
import { SensitivityGrid } from "@/components/finder/SensitivityGrid";
import { Site } from "@/components/shell/Site";

export const metadata: Metadata = {
  title: "What the search can find · Planet Hunter",
  description: "How often the search finds planets of each size and period, measured by hiding fake planets in real TESS light curves.",
};

export default function SensitivityPage() {
  return (
    <Site>
      <SensitivityGrid />
    </Site>
  );
}
