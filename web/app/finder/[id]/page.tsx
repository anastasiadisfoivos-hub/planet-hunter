import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Report } from "@/components/finder/Report";

type Props = { params: Promise<{ id: string }> };

const parseId = (raw: string) => (/^[a-z0-9-]{1,64}$/i.test(raw) ? raw : null);
const ticOf = (id: string) => /^tic(\d+)/i.exec(id)?.[1];

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const id = parseId((await params).id);
  const tic = id ? ticOf(id) : undefined;
  const name = tic ? `TIC ${tic}` : "Candidate";
  return {
    title: `${name} candidate · Planet Hunter Finder`,
    description: `The vetting report for a planet candidate on ${name}: its dip, every check, the pixel check, known-list results and votes.`,
  };
}

export default async function CandidatePage({ params }: Props) {
  const id = parseId((await params).id);
  if (!id) notFound();
  return <Report id={id} />;
}
