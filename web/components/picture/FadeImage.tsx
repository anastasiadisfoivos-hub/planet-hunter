"use client";

import Image, { type ImageProps } from "next/image";
import { useCallback, useState } from "react";

/**
 * next/image that fades in once decoded (DESIGN.md, Motion: 200 ms, opacity only). A picture already in the cache
 * is marked loaded on mount, so it never flashes. The hidden state is CSS-only under `scripting: enabled`, so
 * without JavaScript every picture simply shows.
 */
export function FadeImage(props: ImageProps) {
  const [loaded, setLoaded] = useState(false);
  const ref = useCallback((img: HTMLImageElement | null) => {
    if (img?.complete && img.naturalWidth > 0) setLoaded(true);
  }, []);
  return <Image {...props} ref={ref} data-loaded={loaded || undefined} onLoad={() => setLoaded(true)} alt={props.alt} />;
}
