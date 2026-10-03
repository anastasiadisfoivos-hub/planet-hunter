import type { Metadata } from "next";
import Image from "next/image";
import { TopBar } from "@/components/shell/TopBar";
import { CREDITS, type Credit } from "@/lib/pictures";
import s from "@/components/credits/credits.module.css";

export const metadata: Metadata = {
  title: "Picture credits · Planet Hunter",
  description: "Every picture on Planet Hunter, with its source, credit and licence.",
};

const ORDER = ["ESO", "ESA/Webb", "ESA/Hubble", "NOIRLab", "NASA Image and Video Library", "Helioviewer", "event image", "CDS hips2fits", "Planet Hunter render of TESS data"];
const GROUP: Record<string, string> = {
  ESO: "ESO",
  "ESA/Webb": "ESA/Webb",
  "ESA/Hubble": "ESA/Hubble",
  NOIRLab: "NOIRLab",
  "NASA Image and Video Library": "NASA",
  Helioviewer: "The Sun: NASA SDO via Helioviewer",
  "event image": "Events: each event's own picture",
  "CDS hips2fits": "Survey pictures of stars and event fields",
  "Planet Hunter render of TESS data": "Our renders of real data",
};

export default function CreditsPage() {
  const entries = Object.entries(CREDITS);
  const crops = entries.filter(([k]) => k.startsWith("sky/where/"));
  const rest = entries.filter(([k]) => !k.startsWith("sky/where/"));
  const groups = new Map<string, [string, Credit][]>();
  for (const e of rest) {
    const g = e[1].source;
    groups.set(g, [...(groups.get(g) ?? []), e]);
  }
  const sorted = [...groups.entries()].sort((a, b) => (ORDER.indexOf(a[0]) + 99) % 99 - ((ORDER.indexOf(b[0]) + 99) % 99));
  return (
    <>
      <TopBar />
      <main className={`wrap ${s.page}`}>
        <h1 className={s.h1}>Picture credits</h1>
        <p className={s.line}>
          {entries.length} pictures, every one real. Photographs and instrument data; nothing generated.
        </p>
        {sorted.map(([g, items]) => (
          <section key={g} className={s.group} aria-labelledby={`g-${g}`}>
            <h2 id={`g-${g}`} className="label">
              {GROUP[g] ?? g} · {items.length}
            </h2>
            <ul className={s.list}>
              {items.map(([key, c]) => (
                <li key={key} className={s.row}>
                  <span className={s.thumb}>
                    <Image src={`/images/${key}`} alt="" fill sizes="64px" loading="lazy" style={{ objectFit: "cover" }} />
                  </span>
                  <span className={s.text}>
                    <span className={s.title}>{c.title}</span>
                    <span className={s.credit}>{c.credit}</span>
                    <span className="cap">{c.licence}</span>
                  </span>
                  <a href={c.url} target="_blank" rel="noreferrer" className={s.link}>
                    Source ↗
                  </a>
                </li>
              ))}
            </ul>
          </section>
        ))}
        {crops.length > 0 && (
          <section className={s.group} aria-labelledby="g-where">
            <h2 id="g-where" className="label">
              Where is it · {crops.length}
            </h2>
            <p className={s.credit}>
              The &quot;where is it&quot; view on each event is a crop of ESO&apos;s Milky Way panorama (eso0932a), credit ESO/S. Brunier, CC BY 4.0. Constellation lines
              and names: d3-celestial by Olaf Frohn, BSD-3-Clause.
            </p>
          </section>
        )}
      </main>
    </>
  );
}
