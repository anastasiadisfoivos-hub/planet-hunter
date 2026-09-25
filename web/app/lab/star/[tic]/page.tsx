import type { Metadata } from "next";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { notFound } from "next/navigation";
import { StarLab } from "@/components/lab/star/StarLab";

type Props = { params: Promise<{ tic: string }> };

const parseTic = (raw: string) => (/^\d{1,12}$/.test(raw) ? Number(raw) : null);

/** The star's name for the tab title, from the same hosts file the map uses. */
async function hostName(tic: number): Promise<string | null> {
  try {
    const hosts = JSON.parse(await readFile(path.join(process.cwd(), "public/data/hosts.json"), "utf8")) as { tic: number[]; name: string[] };
    const i = hosts.tic.indexOf(tic);
    return i >= 0 ? hosts.name[i] : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const tic = parseTic((await params).tic);
  const name = tic ? ((await hostName(tic)) ?? `TIC ${tic}`) : "Star";
  return {
    title: `${name} · Planet Hunter Lab`,
    description: `Experiments on ${name} itself: its colour and temperature, its light curve as sound, its planets' sizes and orbits, and what it is made of.`,
  };
}

export default async function StarLabPage({ params }: Props) {
  const tic = parseTic((await params).tic);
  if (!tic) notFound();
  return <StarLab tic={tic} />;
}
