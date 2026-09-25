"use client";

import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react";
import type { StarLab } from "@/lib/api";
import { Skeleton } from "../chart";
import { AbundanceBars, formula, SourceLine, useSpectra, XpChart } from "../Fingerprints";
import { abundancesPath, atmospherePath, elementName, formatTimesSun, gaiaXpPath, speciesName, type Abundances, type Atmosphere, type GaiaXp } from "../spectra";
import { Card } from "./Card";
import s from "./star.module.css";
import l from "../lab.module.css";

export function FingerprintCard({ lab }: { lab: StarLab }) {
  const ab = useSpectra<Abundances>(lab.spectra.abundances ? abundancesPath(lab.tic) : null);
  const xp = useSpectra<GaiaXp>(lab.spectra.gaia_xp ? gaiaXpPath(lab.tic) : null);
  const lede = "What the star is made of, read from the lines in its light, and how its recipe compares with the Sun's.";
  if (!lab.spectra.abundances && !lab.spectra.gaia_xp) {
    return (
      <Card id="fingerprint" title="Fingerprint" lede={lede} locked="No spectrum measured for this star.">
        <p className={l.help}>It unlocks when a survey such as Gaia publishes a spectrum or an element analysis for it.</p>
      </Card>
    );
  }
  const demo = !!(ab.value?.demo || xp.value?.demo);
  const fe = ab.value?.data.elements.find((e) => e.symbol === "Fe");
  return (
    <Card id="fingerprint" title="Fingerprint" data={demo ? "demo" : "real"} lede={lede}>
      <div className={l.bench}>
        <div className={l.chartBox}>
          <div className={l.chartHead}>
            <h3 className={l.h3}>Its recipe against the Sun&apos;s</h3>
            {fe && (
              <span className={l.muted}>
                <span className="mono">{formatTimesSun(fe.x_h_dex)}</span> the Sun&apos;s {elementName("Fe")}
              </span>
            )}
          </div>
          {!lab.spectra.abundances ? (
            <p className={l.help} style={{ padding: "var(--s-4) var(--s-1)" }}>
              No element analysis for this star yet, only its Gaia spectrum.
            </p>
          ) : ab.loading ? (
            <Skeleton label="Loading abundances" />
          ) : ab.value ? (
            <AbundanceBars ab={ab.value.data} />
          ) : (
            <p className={l.help}>The element file is listed but didn&apos;t load.</p>
          )}
        </div>
        <div className={l.side}>
          <div className={l.chartBox}>
            <div className={l.chartHead}>
              <h3 className={l.h3}>Its light, from Gaia</h3>
            </div>
            {!lab.spectra.gaia_xp ? (
              <p className={l.help}>No Gaia spectrum for this star.</p>
            ) : xp.loading ? (
              <Skeleton label="Loading the Gaia spectrum" />
            ) : xp.value ? (
              <XpChart xp={xp.value.data} />
            ) : (
              <p className={l.help}>The Gaia file is listed but didn&apos;t load.</p>
            )}
          </div>
          {ab.value && <SourceLine demo={ab.value.demo} text={ab.value.data.source} />}
          {xp.value && <SourceLine demo={xp.value.demo} text={xp.value.data.credit} />}
          <p className={l.help}>A bar to the right means more of that element than the Sun holds, to the left means less. Measured light, not a photo.</p>
          <Link className={l.linkQuiet} href={`/lab/fingerprints?tic=${lab.tic}`}>
            Read the Sun&apos;s barcode in Chemical fingerprints
            <ArrowRight size={12} aria-hidden />
          </Link>
        </div>
      </div>
    </Card>
  );
}

function AirLink({ slug, fallback }: { slug: string; fallback: string }) {
  const at = useSpectra<Atmosphere>(`planets/${slug}.atmosphere.json`);
  const a = at.value?.data;
  return (
    <li>
      <Link className={s.airLink} href={`/lab/fingerprints?planet=${slug}#planet`}>
        <span className={s.airTitle}>
          {a?.planet ?? fallback}
          <ArrowRight size={14} aria-hidden />
        </span>
        {at.loading ? (
          <span className={l.help}>Loading what was found</span>
        ) : a ? (
          <ul className={l.species} aria-label="Found in its air">
            {a.detections.slice(0, 4).map((d) => (
              <li key={d.species} className={l.speciesItem}>
                <b>{formula(d.species)}</b>
                <span>{speciesName(d.species)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <span className={l.help}>Listed, but the file didn&apos;t load.</span>
        )}
        {at.value?.demo && <span className={l.help}>Demo data</span>}
      </Link>
    </li>
  );
}

export function AirCard({ lab }: { lab: StarLab }) {
  const slugs = lab.spectra.planet_atmospheres;
  const lede = "When a planet crosses its star, starlight shines through its air. The gases there leave their own fingerprints.";
  if (!slugs.length) {
    return (
      <Card
        id="air"
        title="Its planets' air"
        lede={lede}
        locked={
          lab.known_planets.length
            ? `No atmosphere measured yet for ${lab.known_planets.length === 1 ? lab.known_planets[0].name : `any of its ${lab.known_planets.length} planets`}.`
            : "No known planets, so there is no air to read."
        }
      >
        <p className={l.help}>It unlocks when a telescope such as JWST publishes a transmission spectrum of one of them.</p>
      </Card>
    );
  }
  const names = new Map(lab.known_planets.map((p) => [atmospherePath(p.name).replace(/^planets\/|\.atmosphere\.json$/g, ""), p.name]));
  return (
    <Card id="air" title="Its planets' air" lede={lede}>
      <ul className={s.airList}>
        {slugs.map((sl) => (
          <AirLink key={sl} slug={sl} fallback={names.get(sl) ?? sl} />
        ))}
      </ul>
    </Card>
  );
}
