// Loaders for the chemical-fingerprint files. The SPECTRA session writes the real ones to
// /data/spectra/; until a file exists there, the Lab falls back to a DEMO stand-in of the same shape
// in /data/lab/spectra-mock/ and says so.

export type ElementLines = { symbol: string; name: string; lines: { nm: number; relative_intensity: number }[] };

export type SunSpectrum = {
  wavelength_nm: number[];
  flux: number[];
  lines: { nm: number; element: string; label: string }[];
  source: string;
  credit: string;
};

export type Abundances = {
  tic: number;
  name: string;
  source: string;
  elements: { symbol: string; x_h_dex: number; err_dex: number | null }[];
};

export type GaiaXp = { tic: number; wavelength_nm: number[]; flux: number[]; source: string; credit: string };

export type Atmosphere = {
  planet: string;
  detections: { species: string; reference: string }[];
  spectrum: { wavelength_um: number[]; depth_ppm: number[]; err_ppm: number[] } | null;
  source: string;
};

/**
 * Absorption bands made by Earth's own atmosphere (telluric), not by the star. Oxygen: the
 * Fraunhofer A and B bands; water vapour around 720, 820 and 940 nm.
 */
export const TELLURIC_BANDS: { from: number; to: number; species: "O2" | "H2O" }[] = [
  { from: 686, to: 695, species: "O2" },
  { from: 759, to: 771, species: "O2" },
  { from: 716, to: 735, species: "H2O" },
  { from: 810, to: 840, species: "H2O" },
  { from: 890, to: 990, species: "H2O" },
];

const plain = (sym: string) => sym.replace(/[₀-₉]/g, (c) => String(c.charCodeAt(0) - 0x2080));

/**
 * The molecule in Earth's air that made a line in a star's spectrum, or null for a line from the
 * star itself. Recognised by its species (O2, H2O), by a label that says so, or by an oxygen line
 * sitting in one of the oxygen bands.
 */
export function telluricSpecies(line: { nm: number; element: string; label?: string }): "O2" | "H2O" | null {
  const el = plain(line.element).trim();
  if (el === "O2" || el === "H2O") return el;
  const band = TELLURIC_BANDS.find((b) => line.nm >= b.from && line.nm <= b.to);
  if (/earth|telluric|atmospher/i.test(line.label ?? "")) return band?.species ?? (el === "H" ? "H2O" : "O2");
  if (el === "O" && band?.species === "O2") return "O2";
  return null;
}

export type Loaded<T> = { data: T; demo: boolean };

const REAL = "/data/spectra/";
const MOCK = "/data/lab/spectra-mock/";

async function tryJson<T>(url: string, signal?: AbortSignal): Promise<T | null> {
  try {
    const res = await fetch(url, { signal });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch (e) {
    if (signal?.aborted) throw e;
    return null;
  }
}

/** The real file if the SPECTRA session has produced it, else the DEMO stand-in, else null. */
export async function loadSpectra<T>(path: string, signal?: AbortSignal): Promise<Loaded<T> | null> {
  const real = await tryJson<T>(REAL + path, signal);
  if (real) return { data: real, demo: false };
  const mock = await tryJson<T>(MOCK + path, signal);
  return mock ? { data: mock, demo: true } : null;
}

/** Only the real file: used on the sky map, which shows a fingerprint only when real data exists. */
export function loadRealSpectra<T>(path: string, signal?: AbortSignal): Promise<T | null> {
  return tryJson<T>(REAL + path, signal);
}

export const elementsPath = "elements.json";
export const sunPath = "sun_spectrum.json";
export const abundancesPath = (tic: number) => `stars/${tic}.abundances.json`;
export const gaiaXpPath = (tic: number) => `stars/${tic}.gaia_xp.json`;
/** "WASP-121 b" becomes "wasp-121-b". */
export const planetSlug = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
export const atmospherePath = (planet: string) => `planets/${planetSlug(planet)}.atmosphere.json`;

/** "2.1× the Sun's" from a [X/H] in dex. */
export function timesSun(dex: number): number {
  return 10 ** dex;
}

export function formatTimesSun(dex: number): string {
  const x = timesSun(dex);
  return `${x >= 10 ? x.toFixed(0) : x.toFixed(x < 1 ? 2 : 1)}×`;
}

const NAMES: Record<string, string> = {
  H: "hydrogen", He: "helium", Li: "lithium", C: "carbon", N: "nitrogen", O: "oxygen", Na: "sodium", Mg: "magnesium",
  Al: "aluminium", Si: "silicon", S: "sulphur", K: "potassium", Ca: "calcium", Ti: "titanium", V: "vanadium",
  Cr: "chromium", Mn: "manganese", Fe: "iron", Co: "cobalt", Ni: "nickel", Zn: "zinc", Ba: "barium", Y: "yttrium",
};

export function elementName(symbol: string): string {
  return NAMES[symbol] ?? symbol;
}

const MOLECULES: Record<string, string> = {
  H2O: "water", CO2: "carbon dioxide", CO: "carbon monoxide", CH4: "methane", SO2: "sulphur dioxide", NH3: "ammonia",
  TiO: "titanium oxide", VO: "vanadium oxide", HCN: "hydrogen cyanide", H2S: "hydrogen sulphide",
};

export function speciesName(species: string): string {
  return MOLECULES[species] ?? NAMES[species] ?? species;
}
