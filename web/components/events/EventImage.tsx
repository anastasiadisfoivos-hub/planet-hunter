"use client";

import { useState } from "react";
import { Tag } from "@/components/ui";
import type { Image } from "@/lib/contract";
import { imageDisplay, type ImageVariant } from "@/lib/images";
import s from "./events.module.css";

/**
 * One event image, for a feed row (`thumb_url`) or the detail panel (`url`). Rules live in
 * lib/images.ts: cutouts pixelated at 3 to 4x, forecast maps tagged "Forecast", and sky-context
 * captions always visible so nobody reads a years-old archive photo as the event itself.
 */
export function EventImage({ image, variant }: { image: Image; variant: ImageVariant }) {
  const d = imageDisplay(image, variant);
  // Cutouts with no listed size are sized from the loaded image, at the same integer scale.
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  // Cutouts: exact integer-scaled size. Other pictures: their listed size, so the layout reserves the
  // right space before the image arrives (CSS then scales it to the panel width).
  const width = d.width ?? (d.pixelated ? (natural ? natural.w * d.scale! : undefined) : (image.width ?? undefined));
  const height = d.height ?? (d.pixelated ? (natural ? natural.h * d.scale! : undefined) : (image.height ?? undefined));
  const showCaption = variant === "detail" || d.captionAlwaysVisible;

  return (
    <figure className={s.figure} data-variant={variant} data-kind={image.kind}>
      <div className={s.frame}>
        {/* eslint-disable-next-line @next/next/no-img-element -- remote, pre-checked survey images; sizes are exact */}
        <img
          src={d.src}
          alt={d.alt}
          width={width}
          height={height}
          loading="lazy"
          decoding="async"
          className={d.pixelated ? s.pixelated : s.fit}
          onLoad={(e) => d.pixelated && d.width === null && setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
        />
        {d.label && <Tag className={s.label}>{d.label}</Tag>}
      </div>
      {showCaption && (
        <figcaption className={s.caption}>
          <span>{d.caption}</span>
          {d.note && <span className={s.note}>{d.note}</span>}
          {variant === "detail" && (
            <span className={s.credit}>
              {image.credit} · {image.license}
            </span>
          )}
        </figcaption>
      )}
    </figure>
  );
}
