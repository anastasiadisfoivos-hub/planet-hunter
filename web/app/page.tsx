import type { Metadata } from "next";
import { MonitorScreen } from "@/components/monitor/MonitorScreen";
import { Site } from "@/components/shell/Site";

export const metadata: Metadata = {
  title: "Planet Hunter: the monitor",
  description: "The star being searched for planets, its real TESS light curve drawn as it is read, and every dip the search finds, with the reason it was kept or turned down.",
};

export default function Home() {
  return (
    <Site bleed>
      <MonitorScreen />
    </Site>
  );
}
