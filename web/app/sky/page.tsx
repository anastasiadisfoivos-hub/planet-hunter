import type { Metadata } from "next";
import SkyMapApp from "@/components/map/SkyMapApp";

export const metadata: Metadata = {
  title: "Sky · Planet Hunter",
  description: "Supernovae, solar flares, comets, gamma-ray bursts and more from Rubin, ZTF, NASA and others, each at its real position on the sky.",
};

export default function SkyPage() {
  return <SkyMapApp />;
}
