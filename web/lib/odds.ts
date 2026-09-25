// Turn a Poisson mean count into words a player reads at a glance.

function roundNice(n: number): number {
  if (n < 20) return Math.round(n);
  const mag = 10 ** Math.floor(Math.log10(n));
  const step = mag / 2;
  return Math.round(n / step) * step;
}

const fmt = new Intl.NumberFormat("en-US");

/**
 * mean_count λ -> "1 in 40" (chance of at least one), or "about 3" once one is expected.
 */
export function formatOdds(mean: number): string {
  if (!(mean > 0)) return "none expected";
  if (mean >= 1) return mean < 10 ? `about ${Math.round(mean)}` : `about ${fmt.format(roundNice(mean))}`;
  const p = 1 - Math.exp(-mean);
  if (p >= 0.5) return "better than even";
  const oneIn = 1 / p;
  if (oneIn > 100_000) return "less than 1 in 100,000";
  return `1 in ${fmt.format(roundNice(oneIn))}`;
}

export function formatPercent(p: number): string {
  if (p <= 0) return "0%";
  if (p < 0.01) return "under 1%";
  if (p > 0.99) return "over 99%";
  return `${Math.round(p * 100)}%`;
}

export function formatCountdown(ms: number): string {
  if (ms <= 0) return "now";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (d > 0) return `${d}d ${pad(h)}h ${pad(m)}m`;
  return `${pad(h)}:${pad(m)}:${pad(sec)}`;
}
