"use client";

// /events/[id]: the event's picture leads (left); its name, one mono line, three facts and "where is it" sit beside it.
// Explanations are in closed drawers (DESIGN.md, Drawers).

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowUpRight } from "@phosphor-icons/react";
import { CategoryGlyph } from "@/components/map/CategoryGlyph";
import { Drawer } from "@/components/picture/Drawer";
import { Picture } from "@/components/picture/Picture";
import { TypoTile } from "@/components/picture/TypoTile";
import { ButtonLink, DemoTag } from "@/components/ui";
import { API_MOCK, clockNow, getEvent } from "@/lib/api";
import type { SkyEvent } from "@/lib/contract";
import { BASIS_LABEL, categoryOf, SOURCE_LABEL, TYPE_LABEL } from "@/lib/events";
import { formatAgo } from "@/lib/format";
import { constellationOf, type BoundsData, type NamesData } from "@/lib/galactic";
import { eventPic, honesty, pic, sourceName, wherePic } from "@/lib/pictures";
import { formatRa } from "@/lib/sky";
import { CompactSky } from "./CompactSky";
import { dayLabel, longUtc, shortName } from "./text";
import s from "./gallery.module.css";

let names: Promise<[BoundsData, NamesData]> | null = null;
const loadNames = () =>
  (names ??= Promise.all([
    fetch("/data/sky/constellation-bounds.json").then((r) => r.json() as Promise<BoundsData>),
    fetch("/data/sky/constellation-names.json").then((r) => r.json() as Promise<NamesData>),
  ]));

function formatDec(dec: number) {
  const a = Math.abs(dec);
  const d = Math.floor(a);
  const m = Math.floor((a - d) * 60);
  return `${dec < 0 ? "−" : "+"}${String(d).padStart(2, "0")}° ${String(m).padStart(2, "0")}′`;
}

export function EventPage({ id }: { id: string }) {
  const [e, setE] = useState<SkyEvent | null>(null);
  const [now, setNow] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [constellation, setConstellation] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([getEvent(id), clockNow()])
      .then(([ev, t]) => {
        if (!live) return;
        setE(ev);
        setNow(t);
        document.title = `${ev.title} · Planet Hunter`;
        if (ev.location.frame === "sky") {
          const { ra_deg, dec_deg } = ev.location;
          loadNames().then(([b, n]) => live && setConstellation(constellationOf(ra_deg, dec_deg, b, n)), () => undefined);
        }
      })
      .catch((x: unknown) => live && setError(x instanceof Error ? x.message : String(x)));
    return () => {
      live = false;
    };
  }, [id]);

  if (error) {
    return (
      <main className="wrap">
        <div className={s.note} role="alert">
          <p>This event didn&apos;t load. {error}</p>
          <Link href="/events">Back to all events</Link>
        </div>
      </main>
    );
  }
  if (!e) {
    return (
      <main className="wrap" aria-busy="true">
        <div className={s.split} style={{ marginTop: 88 }}>
          <div className={s.skeleton} />
        </div>
      </main>
    );
  }

  const p = eventPic(e.id);
  const cat = categoryOf(e.type);
  const name = shortName(e);
  const loc = e.location;
  const pano = pic("sky/eso0932a-3072.jpg")!;
  const source = SOURCE_LABEL[e.source] ?? e.source;
  const basis = e.confidence_basis === "machine_guess" ? `${Math.round(e.confidence * 100)}%, machine guess` : BASIS_LABEL[e.confidence_basis];
  const skyHref = `/sky?event=${encodeURIComponent(e.id)}`;

  return (
    <main className="wrap" style={{ paddingBottom: "var(--section)" }}>
      <Link href="/events" className={s.crumb}>
        <ArrowLeft size={14} aria-hidden /> Events
      </Link>
      <div className={s.split}>
        <div>
          {p ? (
            <Picture
              pic={p}
              alt={`${TYPE_LABEL[e.type]} ${name}: ${p.title}`}
              sizes="(max-width: 1023px) 100vw, 720px"
              aspect="1 / 1"
              preload
              caption={`${sourceName(p)} · ${p.archive ? "archive, years before the event" : dayLabel(e.observed_at)}`}
              note={honesty(e, p)}
            />
          ) : (
            <TypoTile category={cat} name={name} showName line={`${TYPE_LABEL[e.type]} · ${dayLabel(e.observed_at)} · no picture`} />
          )}
        </div>

        <div className={s.side}>
          <div className={s.kind}>
            <CategoryGlyph category={cat} size={12} />
            <span className="label">{TYPE_LABEL[e.type]}</span>
            {API_MOCK && <DemoTag />}
          </div>
          <h1 className={s.h1}>{name}</h1>
          <p className={`cap ${s.meta}`}>
            {longUtc(e.observed_at)} · {source} · {basis}
          </p>
          <dl className={s.facts}>
            <div>
              <dt className="label">Observed</dt>
              <dd>{now ? formatAgo(e.observed_at, now) : ""}</dd>
            </div>
            {loc.frame === "sky" ? (
              <>
                <div>
                  <dt className="label">In</dt>
                  <dd>{constellation ?? " "}</dd>
                </div>
                <div>
                  <dt className="label">Position</dt>
                  <dd className="mono">
                    {formatRa(loc.ra_deg)} {formatDec(loc.dec_deg)}
                  </dd>
                </div>
              </>
            ) : (
              <div>
                <dt className="label">Where</dt>
                <dd>{loc.frame === "sun" ? "On the Sun" : "Earth's atmosphere"}</dd>
              </div>
            )}
          </dl>

          {loc.frame === "sky" ? (
            <CompactSky ra={loc.ra_deg} dec={loc.dec_deg} errorDeg={loc.error_deg} category={cat} constellation={constellation} crop={wherePic(e.id)} panorama={pano} />
          ) : (
            <p className={s.sunNote}>{loc.frame === "sun" ? "Sun events are not on the night sky." : "Fireballs and storms happen in Earth's atmosphere, not on the sky."}</p>
          )}

          <div className={s.actions}>
            {loc.frame === "sky" && (
              <ButtonLink href={skyHref}>Open in sky</ButtonLink>
            )}
            {e.source_url && (
              <a className={s.crumb} style={{ marginTop: 0 }} href={e.source_url} target="_blank" rel="noreferrer">
                {source} report <ArrowUpRight size={13} aria-hidden />
              </a>
            )}
          </div>
        </div>
      </div>

      <section className={s.more} aria-label="More about this event">
        <Drawer title="How we know" state={basis}>
          <p>{e.summary}</p>
        </Drawer>
        {p && (
          <Drawer title="About the picture" state={p.archive ? "Archive" : sourceName(p)}>
            <p>{p.title}.</p>
            <p>
              {p.credit}. {p.licence}.
            </p>
            {honesty(e, p) && <p>{honesty(e, p)}</p>}
          </Drawer>
        )}
      </section>
    </main>
  );
}
