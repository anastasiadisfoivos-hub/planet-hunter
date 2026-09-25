"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import type { StarLab } from "@/lib/api";
import { LoadError, nf0, Skeleton } from "../chart";
import { blueRedRatio, rgbCss, surfaceBrightnessVsSun, temperatureColor, wienPeakNm } from "../physics";
import { loadLabStars, type LabStar } from "../stars";
import { colourWords, peakWords, SpectrumChart, StarField } from "../Thermometer";
import { Card } from "./Card";
import l from "../lab.module.css";

export function ThermoCard({ lab }: { lab: StarLab }) {
  const [stars, setStars] = useState<LabStar[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [other, setOther] = useState<LabStar | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    loadLabStars(ctl.signal)
      .then(setStars)
      .catch((e: unknown) => !ctl.signal.aborted && setError(e instanceof Error ? e.message : String(e)));
    return () => ctl.abort();
  }, [attempt]);

  // This star's dot: its own catalogue entry, or the bright-star entry that stands for it.
  const self = useMemo(() => stars?.find((st) => st.tic === lab.tic) ?? null, [stars, lab.tic]);

  if (!lab.teff) {
    return (
      <Card id="thermometer" title="Thermometer" lede="A star's colour is a thermometer: its light peaks at a wavelength set by its temperature." locked="No temperature is listed for this star, so there is no curve to draw.">
        <p className={l.help}>Temperatures come from the TESS Input Catalog, via the NASA Exoplanet Archive.</p>
      </Card>
    );
  }

  const teff = lab.teff;
  const peak = wienPeakNm(teff);
  const ratio = blueRedRatio(teff);
  const flux = surfaceBrightnessVsSun(teff);
  return (
    <Card id="thermometer" title="Thermometer" data="real" lede={`${lab.name}'s own light, from its temperature: where it peaks, what colour that makes, and where it sits among the map's stars.`}>
      <div className={l.bench}>
        <div className={l.chartBox}>
          <div className={l.chartHead}>
            <h3 className={l.h3}>Light given off at each wavelength</h3>
          </div>
          <SpectrumChart teff={teff} />
        </div>
        <div className={l.side}>
          <div className={l.block}>
            <div className={l.swatchRow}>
              <span className={l.swatch} style={{ background: rgbCss(temperatureColor(teff)) }} aria-hidden />
              <div>
                <p className={l.big}>{nf0.format(teff)} K</p>
                <p className={l.muted}>Looks {colourWords(teff)}</p>
              </div>
            </div>
          </div>
          <div className={l.block}>
            <dl className={l.readout}>
              <div>
                <dt className="label">Brightest at</dt>
                <dd>{nf0.format(peak)} nm</dd>
              </div>
              <div>
                <dt className="label">Blue vs red</dt>
                <dd>{ratio >= 1 ? `${ratio.toFixed(1)}× bluer` : `${(1 / ratio).toFixed(1)}× redder`}</dd>
              </div>
              <div className={l.readoutWide}>
                <dt className="label">Light per square metre</dt>
                <dd>{flux >= 10 ? nf0.format(flux) : flux.toFixed(2)}× the Sun</dd>
              </div>
            </dl>
            <p className={l.body}>
              Wien&apos;s law: peak = <strong>2,898,000 ÷ {nf0.format(teff)} K</strong> = {nf0.format(peak)} nm, {peakWords(peak)}.
            </p>
          </div>
        </div>
      </div>

      <div className={l.bench}>
        <div className={l.chartBox}>
          <div className={l.chartHead}>
            <h3 className={l.h3}>{lab.name} among the map&apos;s stars</h3>
            {stars && <span className={`${l.help} mono`}>{nf0.format(stars.length)} stars</span>}
          </div>
          {error ? (
            <LoadError
              what="The star catalogues"
              error={error}
              onRetry={() => {
                setError(null);
                setAttempt((n) => n + 1);
              }}
            />
          ) : stars ? (
            <StarField stars={stars} teff={teff} picked={other ?? self} onPick={setOther} labelPicked />
          ) : (
            <Skeleton label="Loading the stars" />
          )}
        </div>
        <div className={l.side}>
          <div className={l.block}>
            {stars && !self && (
              <p className={l.help}>
                This star has no visible-light brightness in the catalogues, so it has no dot here. The dashed line marks its temperature.
              </p>
            )}
            {other && other !== self ? (
              <div className={l.picked} aria-live="polite">
                <p className={l.h3}>{other.name}</p>
                <p className={l.body}>
                  <span className="mono">{nf0.format(other.teff)} K</span>, {other.teff > teff ? "hotter" : other.teff < teff ? "cooler" : "the same temperature"}
                  {other.teff !== teff ? ` than ${lab.name}` : ""}.
                </p>
                <div className={l.controls}>
                  {other.tic && (
                    <Link className={l.linkQuiet} href={`/lab/star/${other.tic}`}>
                      Open its lab
                      <ArrowRight size={12} aria-hidden />
                    </Link>
                  )}
                  <button className={l.linkQuiet} style={{ background: "none", border: 0, padding: 0 }} onClick={() => setOther(null)}>
                    Back to {lab.name}
                  </button>
                </div>
              </div>
            ) : (
              <p className={l.body}>
                The ring marks {lab.name}. Hot stars sit to the right, cool ones to the left; higher dots give off more light. Click another dot to
                compare.
              </p>
            )}
            <p className={l.help}>Dots use the sky map&apos;s colours. Temperatures: TESS Input Catalog for planet hosts, estimated from colour (B−V) for bright stars.</p>
          </div>
        </div>
      </div>
    </Card>
  );
}
