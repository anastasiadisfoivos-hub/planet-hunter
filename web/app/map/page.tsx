import type { Metadata } from "next";
import SkyMapApp from "@/components/map/SkyMapApp";

export const metadata: Metadata = {
  title: "Sky map · Planet Hunter",
  description: "Drag a trap onto the sky and see what Rubin Observatory and TESS might catch there.",
};

export default function MapPage() {
  return <SkyMapApp />;
}
