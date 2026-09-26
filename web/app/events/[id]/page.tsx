import type { Metadata } from "next";
import { EventPage } from "@/components/gallery/EventPage";
import { TopBar } from "@/components/shell/TopBar";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const id = decodeURIComponent((await params).id);
  return { title: `${id} · Events · Planet Hunter` };
}

export default async function EventRoute({ params }: Props) {
  const id = decodeURIComponent((await params).id);
  return (
    <>
      <TopBar />
      <EventPage id={id} />
    </>
  );
}
