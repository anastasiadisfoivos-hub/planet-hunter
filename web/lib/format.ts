// Plain formatting for times, confidence and positions. Numbers are rendered in Geist Mono by callers.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "24 Sep 2026, 01:13 UTC" */
export function formatUtc(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${hh}:${mm} UTC`;
}

/** "14 Jul" this year, "17 Nov 2025" otherwise. */
export function formatDay(iso: string, now: number): string {
  const d = new Date(iso);
  const s = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
  return d.getUTCFullYear() === new Date(now).getUTCFullYear() ? s : `${s} ${d.getUTCFullYear()}`;
}

/** "just now", "12 min ago", "5 h ago", "3 d ago", then a date. */
export function formatAgo(iso: string, now: number): string {
  const min = (now - Date.parse(iso)) / 60000;
  if (min < 1) return "just now";
  if (min < 60) return `${Math.round(min)} min ago`;
  const h = min / 60;
  if (h < 24) return `${Math.round(h)} h ago`;
  const d = h / 24;
  if (d < 30) return `${Math.round(d)} d ago`;
  return formatDay(iso, now);
}

export function formatPercent(x: number): string {
  return `${Math.round(x * 100)}%`;
}

/** Error radius: arcseconds, arcminutes or degrees, whichever reads best. */
export function formatError(deg: number): string {
  if (deg < 1 / 60) return `${(deg * 3600).toFixed(deg * 3600 < 10 ? 1 : 0)}″`;
  if (deg < 1) return `${(deg * 60).toFixed(1)}′`;
  return `${deg.toFixed(1)}°`;
}

export function formatLatLon(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(1)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(1)}° ${lon >= 0 ? "E" : "W"}`;
}
