import type { Metadata } from "next";
import Link from "next/link";
import { Doors } from "@/components/home/Doors";
import { HeroSky } from "@/components/home/HeroSky";
import { KnownSystems } from "@/components/home/KnownSystems";
import { LiveStrip } from "@/components/home/LiveStrip";
import { StarSearch } from "@/components/home/StarSearch";
import s from "@/components/home/home.module.css";

export const metadata: Metadata = {
  title: "Planet Hunter: what is happening in the sky right now",
  description:
    "Supernovae, solar flares, comets and gamma-ray bursts from NASA, Rubin, ZTF and more, experiments on real stars, and real planet candidates. Every result explained in plain words.",
};

const CREDITS_URL = "https://github.com/anastasiadisfoivos-hub/planet-hunter/blob/skymap/web/CREDITS.md";

const HONEST = [
  {
    title: "Real data only",
    text: "Every event, star and light curve comes from a public observatory or catalogue. Anything that is test data carries a DEMO DATA tag.",
  },
  {
    title: "Machine guesses are labelled",
    text: "When a computer sorted something, we say so and show how sure it was, for example “82%, machine guess”.",
  },
  {
    title: "Candidate, never discovered",
    text: "A dip in a star's light is a planet candidate until astronomers confirm it. We don't claim discoveries.",
  },
];

const SOURCES = [
  "NASA Exoplanet Archive",
  "TESS (NASA, via MAST)",
  "Vera C. Rubin Observatory (via Fink)",
  "ZTF (via ALeRCE and Fink)",
  "Transient Name Server",
  "Minor Planet Center",
  "NASA JPL and CNEOS",
  "NASA DONKI",
  "GCN",
  "IceCube",
  "GraceDB",
  "Yale Bright Star Catalogue",
];

export default function Home() {
  return (
    <div className={s.page}>
      <header className={s.nav}>
        <Link href="/" className={s.brand} aria-current="page">
          Planet Hunter
        </Link>
        <nav aria-label="Main">
          <ul className={s.navLinks}>
            <li>
              <Link href="/map">Sky map</Link>
            </li>
            <li>
              <Link href="/lab">Lab</Link>
            </li>
            <li>
              <Link href="/finder">Planet finder</Link>
            </li>
          </ul>
        </nav>
      </header>

      <main>
        <section className={s.hero} aria-labelledby="hero-title">
          <HeroSky />
          <div className={s.heroInner}>
            <h1 id="hero-title" className={s.h1}>
              See what&apos;s happening in the sky right now
            </h1>
            <p className={s.lede}>
              Exploding stars, solar flares, comets and planets around other stars. Real data from NASA, Rubin, ZTF and more,
              with every result explained in plain words.
            </p>
            <StarSearch />
          </div>
        </section>

        <div className={s.wrap}>
          <LiveStrip />
          <Doors />
          <KnownSystems />

          <section className={s.honest} aria-labelledby="honest-title">
            <h2 id="honest-title" className={s.h2}>
              How we stay honest
            </h2>
            <ul className={s.honestList}>
              {HONEST.map((h) => (
                <li key={h.title}>
                  <h3 className={s.h3}>{h.title}</h3>
                  <p>{h.text}</p>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </main>

      <footer className={s.footer}>
        <div className={s.footerInner}>
          <p className={s.footerLead}>
            Data from <span className={s.sources}>{SOURCES.join(", ")}</span>. Pictures keep their own credit and licence.
          </p>
          <a href={CREDITS_URL} className={s.textLink}>
            Data credits and sources
          </a>
        </div>
      </footer>
    </div>
  );
}
