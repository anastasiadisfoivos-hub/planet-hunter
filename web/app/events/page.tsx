import type { Metadata } from "next";
import { Gallery } from "@/components/gallery/Gallery";
import { TopBar } from "@/components/shell/TopBar";

export const metadata: Metadata = {
  title: "Events · Planet Hunter",
  description: "What happened in the sky, newest first: each event's own picture, from NASA, ZTF, Rubin, TNS and more.",
};

export default function EventsPage() {
  return (
    <>
      <TopBar />
      <Gallery />
    </>
  );
}
