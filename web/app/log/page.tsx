import type { Metadata } from "next";
import { Log } from "@/components/monitor/Log";
import { Site } from "@/components/shell/Site";

export const metadata: Metadata = {
  title: "Log · Planet Hunter",
  description: "Every star the planet search has looked at, when, with which TESS data, and what it found; and where in the sky it has looked.",
};

export default function LogPage() {
  return (
    <Site>
      <Log />
    </Site>
  );
}
