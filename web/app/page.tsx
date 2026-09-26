import type { Metadata } from "next";
import Link from "next/link";
import { Candidates } from "@/components/home/Candidates";
import { ThisWeek } from "@/components/home/ThisWeek";
import { Drawer } from "@/components/picture/Drawer";
import { Info } from "@/components/picture/Info";
import { Picture } from "@/components/picture/Picture";
import { TopBar } from "@/components/shell/TopBar";
import { CREDITS, honesty, pic, sourceName, starPic } from "@/lib/pictures";
import s from "@/components/home/home.module.css";

export const metadata: Metadata = {
  title: "Planet Hunter: the sky this week, in real pictures",
  description: "Supernovae, solar flares, comets and bursts, each with its own real picture; experiments on real stars; and real planet candidates.",
};

const LAB = [
  { name: "Star thermometer", href: "/lab/thermometer", key: "feature/heic0715a.jpg" },
  { name: "Hear a star", href: "/lab/hear-a-star", key: "data/wasp18-tess-pixels-s0104.png" },
  { name: "Hubble diagram", href: "/lab/hubble", key: "feature/heic0406a.jpg" },
  { name: "Chemical fingerprints", href: "/lab/fingerprints", key: "events/donki-2026-09-19T17-57-00-FLR-001.jpg" },
] as const;

const FAMOUS = [
  { name: "WASP-18", tic: 100100827 },
  { name: "WASP-121", tic: 22529346 },
  { name: "WASP-43", tic: 36734222 },
  { name: "TOI-700", tic: 150428135 },
] as const;

export default function Home() {
  const hero = pic("sky/eso0733a.jpg")!;
  return (
    <>
      <TopBar over />
      <main>
        <section className={s.hero} aria-labelledby="hero-title">
          <Picture pic={hero} alt="The Milky Way's centre over the Very Large Telescope at Paranal, with a laser guide star" sizes="100vw" preload quality={85} objectPosition="50% 60%" className={s.heroPic} />
          <div className={`wrap ${s.heroCopy}`}>
            <h1 id="hero-title" className={s.display}>
              The sky this week, in real pictures.
            </h1>
          </div>
        </section>
        <div className="wrap">
          <div className={s.heroCap}>
            <span className="cap">ESO/Y. Beletsky · Paranal Observatory</span>
            <Info pic={hero} />
          </div>
        </div>

        <ThisWeek />
        <Candidates />

        <section className={`wrap ${s.sec}`} aria-labelledby="lab">
          <div className={s.shead}>
            <div>
              <h2 id="lab" className={s.h2}>
                Lab
              </h2>
              <p className={s.line}>Experiments on real stars.</p>
            </div>
            <Link href="/lab" className={s.more}>
              Open the lab →
            </Link>
          </div>
          <div className={s.row4}>
            {LAB.map((l) => {
              const p = pic(l.key)!;
              return (
                <figure key={l.name} className={s.card}>
                  <Link href={l.href} className={s.hit}>
                    <Picture pic={p} alt={p.title} sizes="(max-width: 639px) 50vw, 320px" aspect="3 / 4" />
                    <span className={s.name}>{l.name}</span>
                  </Link>
                  <figcaption className={s.capline}>
                    <span className="cap">{sourceName(p)}</span>
                    <Info pic={p} note={honesty(null, p)} />
                  </figcaption>
                </figure>
              );
            })}
          </div>
        </section>

        <section className={`wrap ${s.sec}`} aria-labelledby="famous">
          <div className={s.shead}>
            <h2 id="famous" className={s.h2}>
              Famous stars
            </h2>
          </div>
          <div className={s.row4}>
            {FAMOUS.map((f) => {
              const p = starPic(f.tic)!;
              return (
                <figure key={f.tic} className={s.card}>
                  <Link href={`/lab/star/${f.tic}`} className={s.hit}>
                    <Picture pic={p} alt={`Survey picture of the sky around ${f.name}; the crosshair marks the star`} sizes="(max-width: 639px) 50vw, 320px" aspect="1 / 1" />
                    <span className={s.name}>{f.name}</span>
                  </Link>
                  <figcaption className={s.capline}>
                    <span className="cap">{sourceName(p)} · archive</span>
                    <Info pic={p} note={honesty(null, p)} />
                  </figcaption>
                </figure>
              );
            })}
          </div>
        </section>

        <section className={`wrap ${s.sec} ${s.end}`} aria-label="Honesty and credits">
          <Drawer title="How we stay honest" state="3 rules">
            <p>Every picture is real and credited: tap i on any picture for its source and licence. Survey pictures marked archive were taken years before the event, and a crosshair marks where it happened.</p>
            <p>When a computer sorted something, the caption says guess and how sure it was.</p>
            <p>A dip in a star&apos;s light is a planet candidate until astronomers confirm it.</p>
          </Drawer>
          <Drawer title="Picture credits" state={`${Object.keys(CREDITS).length} pictures`}>
            <p>
              NASA, ESA/Webb, ESA/Hubble, ESO, NOIRLab, SDO via Helioviewer, and survey pictures cut with CDS hips2fits. <Link href="/credits">Every credit and licence</Link>.
            </p>
          </Drawer>
        </section>
      </main>
    </>
  );
}
