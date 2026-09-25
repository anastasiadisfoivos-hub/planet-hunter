"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { abundancesPath, elementName, formatTimesSun, loadRealSpectra, type Abundances } from "./spectra";
import s from "./lab.module.css";

/**
 * "Chemical fingerprint" for the star panel on the map. Renders only when the SPECTRA session has
 * published real abundances for this TIC; never shows demo numbers on the map.
 */
export function ChemicalFingerprint({ tic }: { tic: number }) {
  const [ab, setAb] = useState<{ tic: number; data: Abundances | null } | null>(null);
  useEffect(() => {
    const ctl = new AbortController();
    loadRealSpectra<Abundances>(abundancesPath(tic), ctl.signal)
      .then((data) => setAb({ tic, data }))
      .catch(() => {});
    return () => ctl.abort();
  }, [tic]);
  const data = ab?.tic === tic ? ab.data : null;
  if (!data || !data.elements.length) return null;
  const shown = [...data.elements].sort((a, b) => (a.symbol === "Fe" ? -1 : b.symbol === "Fe" ? 1 : 0)).slice(0, 6);
  return (
    <section className={s.fingerprint} aria-labelledby={`fp-${tic}`}>
      <h3 id={`fp-${tic}`} className={s.fingerprintTitle}>
        Chemical fingerprint
      </h3>
      <ul className={s.fingerprintList}>
        {shown.map((e) => (
          <li key={e.symbol}>
            <span className="mono">{formatTimesSun(e.x_h_dex)}</span>
            <span>{elementName(e.symbol)}</span>
          </li>
        ))}
      </ul>
      <p className={s.help}>
        How much of each element it holds, compared with the Sun. Measured from the lines in its light, not a photo. {data.source}.
      </p>
      <Link className={s.linkQuiet} href={`/lab/fingerprints?tic=${tic}`}>
        Compare with the Sun in the Lab
        <ArrowRight size={12} aria-hidden />
      </Link>
    </section>
  );
}
