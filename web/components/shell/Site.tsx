import Link from "next/link";
import { TopBar } from "./TopBar";
import s from "./shell.module.css";

/** Every page of the new site: paper, the top bar, the page, and a footer with the data's sources. */
export function Site({ children, end, bleed = false }: { children: React.ReactNode; end?: React.ReactNode; bleed?: boolean }) {
  return (
    <div className="site">
      <TopBar end={end} />
      <main id="main" className={bleed ? s.bleed : s.main}>
        {children}
      </main>
      <footer className={`wrap ${s.foot}`}>
        <p className="label">Light curves: NASA TESS, SPOC pipeline, via MAST</p>
        <p className="label">Stars: TESS Input Catalog · Gaia DR3 · AAVSO VSX</p>
        <p className="label">
          <Link href="/methods">How the search works</Link>
        </p>
      </footer>
    </div>
  );
}
