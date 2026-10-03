import Link from "next/link";
import { TessGlyph } from "@/components/monitor/Glyphs";
import { TopBar } from "./TopBar";
import s from "./shell.module.css";

/** Every page of the new site: paper, the top bar, the page, and a footer with the data's sources. */
export function Site({ children, end, bleed = false }: { children: React.ReactNode; end?: React.ReactNode; bleed?: boolean }) {
  return (
    <div className="site">
      <a href="#main" className={s.skip}>
        Skip to the page
      </a>
      <TopBar end={end} />
      <main id="main" className={bleed ? s.bleed : s.main}>
        {children}
      </main>
      <footer className={`wrap ${s.foot}`}>
        <TessGlyph size={48} />
        <p className={s.credit}>
          Light curves from NASA&apos;s TESS, SPOC pipeline, via MAST. Stars from the TESS Input Catalog, Gaia DR3 and AAVSO VSX.
        </p>
        <p className={s.footLink}>
          <Link href="/methods">How the search works</Link>
        </p>
      </footer>
    </div>
  );
}
