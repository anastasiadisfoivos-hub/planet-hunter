import Link from "next/link";
import { CategoryGlyph } from "@/components/map/CategoryGlyph";
import { Picture } from "@/components/picture/Picture";
import { Info } from "@/components/picture/Info";
import { TypoTile } from "@/components/picture/TypoTile";
import type { SkyEvent } from "@/lib/contract";
import { categoryOf, TYPE_LABEL } from "@/lib/events";
import { eventFlag, eventPic, honesty } from "@/lib/pictures";
import { dayLabel, eventHref, shortName } from "./text";
import s from "./gallery.module.css";

/** One event: its own picture (or the typographic tile), its name, and one caption line with the i. */
export function EventTile({ event: e, sizes, big, className }: { event: SkyEvent; sizes: string; big?: boolean; className?: string }) {
  const p = eventPic(e.id);
  const cat = categoryOf(e.type);
  const name = shortName(e);
  const flag = eventFlag(e, p);
  return (
    <figure className={`${s.tile} ${big ? s.big : ""} ${className ?? ""}`}>
      <Link href={eventHref(e.id)} className={s.hit} title={TYPE_LABEL[e.type]}>
        {p ? (
          <Picture pic={p} alt={`${TYPE_LABEL[e.type]} ${name}: ${p.title}`} sizes={sizes} aspect={big ? undefined : "1 / 1"} className={s.pic} />
        ) : (
          <TypoTile category={cat} name={name} line={`${TYPE_LABEL[e.type]} · ${dayLabel(e.observed_at)}`} />
        )}
        <span className={s.name}>
          <CategoryGlyph category={cat} size={10} />
          <b>{name}</b>
        </span>
      </Link>
      <figcaption className={s.capline}>
        <span className="cap">{flag || dayLabel(e.observed_at)}</span>
        {p && <Info pic={p} note={honesty(e, p)} />}
      </figcaption>
    </figure>
  );
}
