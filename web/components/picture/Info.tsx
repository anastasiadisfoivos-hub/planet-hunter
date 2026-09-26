"use client";

import { useId } from "react";
import type { Pic } from "@/lib/pictures";
import s from "./picture.module.css";

/** The i at the end of a caption line: title, credit, licence, source link and one honesty sentence (native popover). */
export function Info({ pic, note }: { pic: Pic; note?: string | null }) {
  const id = `info-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  return (
    <>
      <button type="button" className={s.info} popoverTarget={id} aria-label={`About this picture: ${pic.title}`}>
        i
      </button>
      <div id={id} popover="auto" className={s.pop}>
        <p className={s.popTitle}>{pic.title}</p>
        {note && <p>{note}</p>}
        <p>{pic.credit}</p>
        <p className="cap">{pic.licence}</p>
        <a href={pic.url} target="_blank" rel="noreferrer" className={s.popLink}>
          Source ↗
        </a>
      </div>
    </>
  );
}
