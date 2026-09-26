// File names for pictures in public/images/, shared by the build scripts and the pages.

/** "tns:2026abvs" → "tns-2026abvs": event ids made safe for file names. */
export function pictureKey(id: string): string {
  return id.replace(/[:/]/g, "-").replace(/\s+/g, "_");
}

/** The compact "where is it" sky: galactic longitude × latitude span, in degrees. */
export const WHERE_SPAN = { l: 56, b: 34 } as const;
