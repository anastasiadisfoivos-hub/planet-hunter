import type { Metadata } from "next";
import { Methods } from "@/components/monitor/Methods";
import { Site } from "@/components/shell/Site";

export const metadata: Metadata = {
  title: "How the search works · Planet Hunter",
  description: "From a star's light to a planet candidate: the data, the search, the checks, the pixel check, vetting and votes.",
};

export default function MethodsPage() {
  return (
    <Site>
      <Methods />
    </Site>
  );
}
