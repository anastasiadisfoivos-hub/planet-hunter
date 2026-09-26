"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { EmptyState } from "@/components/ui";
import { ApiError, getStarLab, getStarLightcurve, type Served, type StarLab as Lab, type StarLightcurve } from "@/lib/api";
import { LoadError, nf0 } from "../chart";
import { rgbCss, temperatureColor } from "../physics";
import { AirCard, FingerprintCard } from "./SpectraCards";
import { HearCard } from "./HearCard";
import { KeplerCard } from "./KeplerCard";
import { MeasureCard } from "./MeasureCard";
import { starMass } from "./shared";
import { ThermoCard } from "./ThermoCard";
import { Picture } from "@/components/picture/Picture";
import { honesty, sourceName, starPic } from "@/lib/pictures";
import s from "./star.module.css";
import l from "../lab.module.css";

function Header({ lab, demo }: { lab: Lab; demo: boolean }) {
  const ready = [
    !!lab.teff,
    lab.lightcurve.available,
    lab.lightcurve.available && lab.signals.length > 0 && !!lab.radius,
    lab.spectra.gaia_xp || lab.spectra.abundances,
    lab.spectra.planet_atmospheres.length > 0,
    lab.known_planets.some((p) => p.period_d) && (!!lab.mass || !!lab.teff),
  ].filter(Boolean).length;
  return (
    <>
      <header className={s.head}>
        <span
          className={`${s.dot} ${lab.teff ? "" : s.dotEmpty}`}
          style={lab.teff ? { background: rgbCss(temperatureColor(lab.teff)) } : undefined}
          title={lab.teff ? `Its colour at ${nf0.format(lab.teff)} K` : "No temperature listed"}
          aria-hidden
        />
        <div className={s.headText}>
          <div className={l.titleRow}>
            <h1 className={l.h1}>{lab.name}</h1>
          </div>
          <dl className={s.facts}>
            <div>
              <dt className="label">TIC</dt>
              <dd>{lab.tic}</dd>
            </div>
            <div>
              <dt className="label">Temperature</dt>
              <dd>{lab.teff ? `${nf0.format(lab.teff)} K` : "not listed"}</dd>
            </div>
            <div>
              <dt className="label">Radius</dt>
              <dd>{lab.radius ? `${lab.radius < 10 ? lab.radius.toFixed(2) : nf0.format(lab.radius)} R☉` : "not listed"}</dd>
            </div>
            <div>
              <dt className="label">Distance</dt>
              <dd>
                {lab.distance ? `${nf0.format(lab.distance * 3.2616)} light-years` : "not listed"}
              </dd>
            </div>
            <div>
              <dt className="label">TESS mag</dt>
              <dd>{lab.tmag != null ? lab.tmag.toFixed(2) : "not listed"}</dd>
            </div>
          </dl>
        </div>
        {starPic(lab.tic) && (
          <Picture
            pic={starPic(lab.tic)!}
            alt={`Survey picture of the sky around ${lab.name}; the crosshair marks the star`}
            sizes="200px"
            aspect="1 / 1"
            caption={`${sourceName(starPic(lab.tic)!)} · archive`}
            note={honesty(null, starPic(lab.tic)!)}
            className={s.headPic}
          />
        )}
        <div className={s.headActions}>
          <Link className={s.ghostLink} href={`/sky?host=${lab.tic}`}>
            Fly to it
            <ArrowRight size={14} aria-hidden />
          </Link>
        </div>
      </header>
      <div className={s.summary}>
        <p className={l.body}>
          Six experiments on this one star. <span className="mono">{ready}</span> of 6 have the data they need; the others say what is missing.
        </p>
        {demo && (
          <p className={l.help} style={{ maxWidth: "60ch" }}>
            Star facts and planets are NASA Exoplanet Archive values. Cards marked DEMO DATA use stand-in data.
          </p>
        )}
      </div>
    </>
  );
}

export function StarLab({ tic }: { tic: number }) {
  const [served, setServed] = useState<Served<Lab> | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [lc, setLc] = useState<Served<StarLightcurve> | null>(null);
  const [lcError, setLcError] = useState<string | null>(null);
  const [lcAttempt, setLcAttempt] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    getStarLab(tic, ctl.signal)
      .then((v) => {
        setServed(v);
        setError(null);
      })
      .catch((e: unknown) => {
        if (ctl.signal.aborted) return;
        setError({ status: e instanceof ApiError ? e.status : 0, message: e instanceof Error ? e.message : String(e) });
      });
    return () => ctl.abort();
  }, [tic, attempt]);

  const available = served?.data.lightcurve.available ?? false;
  useEffect(() => {
    if (!available) return;
    const ctl = new AbortController();
    getStarLightcurve(tic, ctl.signal)
      .then((v) => {
        setLc(v);
        setLcError(null);
      })
      .catch((e: unknown) => !ctl.signal.aborted && setLcError(e instanceof Error ? e.message : String(e)));
    return () => ctl.abort();
  }, [tic, available, lcAttempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  if (error) {
    return error.status === 404 ? (
      <EmptyState
        title={`No lab for TIC ${tic}`}
        action={
          <Link className={s.ghostLink} href="/sky">
            Pick a star on the sky
          </Link>
        }
      >
        Star labs exist for the planet hosts on the sky map. This TIC number isn&apos;t one of them.
      </EmptyState>
    ) : (
      <LoadError what="This star's lab" error={error.message} onRetry={reload} />
    );
  }
  if (!served) {
    return (
      <div className={s.cards} aria-busy="true">
        <div className={l.skeleton} style={{ height: 120 }} role="status">
          <span className="sr-only">Loading the star</span>
        </div>
        <div className={l.skeleton} style={{ height: 480 }} />
      </div>
    );
  }

  const lab = served.data;
  const mass = starMass(lab);
  const standIn = served.standIn;
  const curve = available ? (lc?.data ?? null) : null;
  return (
    <>
      <Header lab={lab} demo={served.demo} />
      <div className={s.cards}>
        <ThermoCard lab={lab} />
        <HearCard lab={lab} lc={curve} standIn={standIn} lcError={lcError} onRetry={() => setLcAttempt((n) => n + 1)} onAnalyzed={reload} />
        <MeasureCard lab={lab} lc={curve} standIn={standIn} mass={mass} lcError={lcError} />
        <FingerprintCard lab={lab} />
        <AirCard lab={lab} />
        <KeplerCard lab={lab} mass={mass} />
      </div>
    </>
  );
}
