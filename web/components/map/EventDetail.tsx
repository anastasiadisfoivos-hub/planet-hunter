"use client";

import { ArrowSquareOut, Crosshair, X } from "@phosphor-icons/react";
import { Button, ButtonLink, DataGrid, Tag } from "@/components/ui";
import { EventImage } from "@/components/events/EventImage";
import { CATEGORY_OF, type Image, type SkyEvent } from "@/lib/contract";
import { BASIS_LABEL, SOURCE_LABEL, TYPE_LABEL } from "@/lib/events";
import { formatAgo, formatError, formatPercent, formatUtc } from "@/lib/format";
import { cutoutScale } from "@/lib/images";
import { formatDec, formatRa } from "@/lib/sky";
import { CategoryGlyph } from "./CategoryGlyph";
import { EarthInset } from "./EarthInset";
import s from "./map.module.css";

const CUTOUT_ORDER = ["cutout_reference", "cutout_new", "cutout_difference"] as const;
const CUTOUT_LABEL: Record<(typeof CUTOUT_ORDER)[number], string> = {
  cutout_reference: "Reference",
  cutout_new: "New",
  cutout_difference: "Difference",
};

/** The three survey cutouts side by side, pixelated at 3 to 4 times their size, with one shared credit. */
function Cutouts({ images }: { images: Image[] }) {
  const byKind = new Map(images.map((i) => [i.kind, i]));
  const shown = CUTOUT_ORDER.filter((k) => byKind.has(k));
  if (!shown.length) return null;
  const credit = byKind.get(shown[0])!;
  return (
    <figure className={s.cutouts}>
      <div className={s.cutoutRow}>
        {shown.map((k) => {
          const img = byKind.get(k)!;
          const px = img.width ? img.width * cutoutScale(img.width) : undefined;
          return (
            <div key={k} className={s.cutout}>
              {/* eslint-disable-next-line @next/next/no-img-element -- survey cutouts, shown pixel for pixel */}
              <img src={img.url} alt={img.caption} width={px} height={px} className={s.pixelated} loading="lazy" />
              <span className="label">{CUTOUT_LABEL[k]}</span>
            </div>
          );
        })}
      </div>
      <figcaption className={s.caption}>
        <span>Reference is the sky before; new is the latest image; difference is new minus reference, so only what changed shows.</span>
        <span className={s.credit}>
          {credit.credit} · {credit.license}
        </span>
      </figcaption>
    </figure>
  );
}

function Pictures({ images }: { images: Image[] }) {
  if (!images.length) return null;
  const first = images.filter((i) => i.kind === "sky_context");
  const middle = images.filter((i) => i.kind === "solar" || i.kind === "forecast_map");
  const rest = images.filter((i) => !["sky_context", "solar", "forecast_map", ...CUTOUT_ORDER].includes(i.kind));
  return (
    <section className={s.pictures} aria-label="Pictures">
      {first.map((img) => (
        <EventImage key={img.url} image={img} variant="detail" />
      ))}
      {middle.map((img) => (
        <EventImage key={img.url} image={img} variant="detail" />
      ))}
      <Cutouts images={images} />
      {rest.map((img) => (
        <EventImage key={img.url} image={img} variant="detail" />
      ))}
    </section>
  );
}

function where(e: SkyEvent): { label: string; value: string; mono: boolean; hint?: string } {
  const l = e.location;
  if (l.frame === "sky") {
    return { label: "Position", value: `${formatRa(l.ra_deg)}  ${formatDec(l.dec_deg)}`, mono: true, hint: `Within ${formatError(l.error_deg)}` };
  }
  if (l.frame === "sun") return { label: "Where", value: "On the Sun", mono: false, hint: "Marker placed at the Sun's position now" };
  return { label: "Where", value: "At Earth", mono: false };
}

export function EventDetail({ event: e, now, onBack, onShow }: { event: SkyEvent; now: number; onBack: () => void; onShow: (e: SkyEvent) => void }) {
  const cat = CATEGORY_OF[e.type];
  const w = where(e);
  const loc = e.location;
  const note = typeof e.raw?.location_note === "string" ? e.raw.location_note : null;
  return (
    <article className={s.detail} aria-label={e.title}>
      <div className={s.detailHead}>
        <Button variant="quiet" size="sm" icon={<X size={16} />} onClick={onBack}>
          Close
        </Button>
        {e.source === "rubin" && e.raw?.from_latest_observed_window === true && <Tag>Rubin, latest nights</Tag>}
        <ButtonLink href={`/events/${encodeURIComponent(e.id)}`} variant="quiet" size="sm">
          Event page →
        </ButtonLink>
      </div>

      <div className={s.stackTight}>
        <p className={`mono ${s.rowType}`}>
          <CategoryGlyph category={cat} size={10} />
          {TYPE_LABEL[e.type]} · {SOURCE_LABEL[e.source] ?? e.source}
        </p>
        <h2 className={s.detailTitle}>{e.title}</h2>
      </div>

      <Pictures images={e.images} />
      {loc.frame === "earth" && <EarthInset lat={loc.lat_deg} lon={loc.lon_deg} altKm={loc.alt_km} note={note} />}

      <p className={s.summary}>{e.summary}</p>

      <DataGrid
        items={[
          { label: "Observed", value: formatUtc(e.observed_at), mono: true, hint: formatAgo(e.observed_at, now), wide: true },
          { label: "Confidence", value: formatPercent(e.confidence), mono: true, hint: BASIS_LABEL[e.confidence_basis] },
          e.brightness_mag != null
            ? { label: "Brightness", value: `${e.brightness_mag.toFixed(1)} mag`, mono: true }
            : e.raw?.reported_at_known === false
              ? { label: "Reported", value: "Report time not published", mono: false }
              : { label: "Reported", value: formatAgo(e.reported_at, now), mono: true },
          { ...w },
        ]}
      />

      <div className={s.actions}>
        {loc.frame !== "earth" && (
          <Button variant="primary" icon={<Crosshair size={16} />} onClick={() => onShow(e)}>
            Show on map
          </Button>
        )}
        <a className={s.linkButton} href={e.source_url} target="_blank" rel="noreferrer">
          {SOURCE_LABEL[e.source] ?? e.source} page
          <ArrowSquareOut size={14} aria-hidden />
        </a>
      </div>
    </article>
  );
}
