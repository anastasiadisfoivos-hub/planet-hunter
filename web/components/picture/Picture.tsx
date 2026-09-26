import Image from "next/image";
import { FadeImage } from "./FadeImage";
import type { Pic } from "@/lib/pictures";
import { Info } from "./Info";
import s from "./picture.module.css";

type Props = {
  pic: Pic;
  alt: string;
  /** `sizes` for the responsive srcset (DESIGN.md: responsive sizes, lazy below the fold). */
  sizes: string;
  /** CSS aspect ratio of the frame, e.g. "1 / 1". Omit to fill the parent (the parent sets the size). */
  aspect?: string;
  /** Load first: only the one hero picture above the fold. */
  preload?: boolean;
  /** Draw the crosshair at the picture's mark (archive and survey pictures). Default: when it has one. */
  mark?: boolean;
  /** The caption line: omit to draw the frame only (a tile adds its own line). */
  caption?: string | null;
  /** Extra sentence for the i. */
  note?: string | null;
  objectPosition?: string;
  className?: string;
  fit?: "cover" | "contain";
  quality?: 75 | 85;
};

/** A real picture in a frame, with its crosshair and, optionally, its caption line and i. */
export function Picture({ pic, alt, sizes, aspect, preload, mark, caption, note, objectPosition, className, fit = "cover", quality = 75 }: Props) {
  const showMark = (mark ?? true) && pic.mark;
  // The one preloaded hero picture shows at once; everything else fades in when decoded.
  const frame = (
    <div className={s.frame} style={aspect ? { aspectRatio: aspect } : undefined} data-fill={aspect ? undefined : true}>
      {preload ? (
        <Image data-loaded src={pic.src} alt={alt} fill sizes={sizes} quality={quality} preload className={s.img} style={{ objectFit: fit, objectPosition }} />
      ) : (
        <FadeImage src={pic.src} alt={alt} fill sizes={sizes} quality={quality} loading="lazy" className={s.img} style={{ objectFit: fit, objectPosition }} />
      )}
      {showMark && <Crosshair u={pic.mark!.u} v={pic.mark!.v} />}
    </div>
  );
  if (caption === undefined) return <div className={className}>{frame}</div>;
  return (
    <figure className={`${s.figure} ${className ?? ""}`}>
      {frame}
      <figcaption className={s.capline}>
        <span className={`cap ${s.capText}`}>{caption}</span>
        <Info pic={pic} note={note} />
      </figcaption>
    </figure>
  );
}

/** A thin crosshair (1px ink, a gap at the centre) where the event or target star is. */
export function Crosshair({ u, v }: { u: number; v: number }) {
  return (
    <svg className={s.crosshair} style={{ left: `${u * 100}%`, top: `${v * 100}%` }} viewBox="-16 -16 32 32" aria-hidden>
      <path d="M-15 0h9M6 0h9M0 -15v9M0 6v9" />
    </svg>
  );
}
