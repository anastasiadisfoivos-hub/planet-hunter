import type { Metadata } from "next";
import Link from "next/link";
import { Drawer } from "@/components/picture/Drawer";
import { Info } from "@/components/picture/Info";
import { Picture } from "@/components/picture/Picture";
import { DemoTag } from "@/components/ui";
import { honesty, pic, sourceName, starPic } from "@/lib/pictures";
import s from "@/components/lab/index.module.css";

export const metadata: Metadata = {
  title: "Lab · Planet Hunter",
  description: "Small experiments with real starlight: a star thermometer, a light curve you can hear, a Hubble diagram and chemical fingerprints.",
};

const EXPERIMENTS = [
  { href: "/lab/thermometer", title: "Star thermometer", key: "feature/heic0715a.jpg", demo: false },
  { href: "/lab/hear-a-star", title: "Hear a star", key: "data/wasp18-tess-pixels-s0104.png", demo: false },
  { href: "/lab/hubble", title: "Hubble diagram", key: "feature/heic0406a.jpg", demo: true },
  { href: "/lab/fingerprints", title: "Chemical fingerprints", key: "events/donki-2026-09-19T17-57-00-FLR-001.jpg", demo: true },
] as const;

const STARS = [
  { name: "WASP-18", tic: 100100827 },
  { name: "WASP-121", tic: 22529346 },
  { name: "WASP-43", tic: 36734222 },
  { name: "TOI-700", tic: 150428135 },
] as const;

export default function LabIndex() {
  const hero = pic("feature/weic2205a.jpg")!;
  return (
    <main>
      <section className={s.hero} aria-labelledby="lab-title">
        <Picture pic={hero} alt="The Cosmic Cliffs of the Carina Nebula, seen by the James Webb Space Telescope" sizes="100vw" preload quality={85} objectPosition="50% 70%" className={s.heroPic} />
        <div className={`wrap ${s.heroCopy}`}>
          <h1 id="lab-title" className={s.display}>
            Lab
          </h1>
          <p className={s.heroLine}>Experiments on real stars.</p>
        </div>
      </section>
      <div className="wrap">
        <div className={s.capline}>
          <span className="cap">NASA, ESA, CSA, STScI · Webb, Carina Nebula</span>
          <Info pic={hero} />
        </div>
      </div>

      <section className={`wrap ${s.sec}`} aria-label="Experiments">
        <ul className={s.grid2}>
          {EXPERIMENTS.map((e) => {
            const p = pic(e.key)!;
            return (
              <li key={e.href} className={s.item}>
                <Link href={e.href} className={s.hit}>
                  <Picture pic={p} alt={p.title} sizes="(max-width: 639px) 100vw, 640px" aspect="4 / 3" />
                  <span className={s.name}>
                    {e.title}
                    {e.demo && <DemoTag />}
                  </span>
                </Link>
                <div className={s.capline}>
                  <span className="cap">{sourceName(p)}</span>
                  <Info pic={p} note={honesty(null, p)} />
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className={`wrap ${s.sec}`} aria-labelledby="starlabs">
        <div className={s.shead}>
          <h2 id="starlabs" className={s.h2}>
            Star labs
          </h2>
          <p className={s.line}>One star, every experiment.</p>
        </div>
        <ul className={s.row4}>
          {STARS.map((st) => {
            const p = starPic(st.tic)!;
            return (
              <li key={st.tic} className={s.item}>
                <Link href={`/lab/star/${st.tic}`} className={s.hit}>
                  <Picture pic={p} alt={`Survey picture of the sky around ${st.name}; the crosshair marks the star`} sizes="(max-width: 639px) 50vw, 320px" aspect="1 / 1" />
                  <span className={s.name}>{st.name}</span>
                </Link>
                <div className={s.capline}>
                  <span className="cap">{sourceName(p)} · archive</span>
                  <Info pic={p} note={honesty(null, p)} />
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className={`wrap ${s.sec} ${s.end}`} aria-label="About the lab">
        <Drawer title="What the lab is" state="About">
          <p>Small experiments with real starlight. They use the same stars and the same analysis results as the sky and the Finder.</p>
          <p>Experiments marked DEMO DATA run on stand-in numbers until their real sources are connected: live supernovae from the Transient Name Server, and measured spectra.</p>
          <p>Every star with known planets has its own lab. Find one with the search in the top bar.</p>
        </Drawer>
      </section>
    </main>
  );
}
