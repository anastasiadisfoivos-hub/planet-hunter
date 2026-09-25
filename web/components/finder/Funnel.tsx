import type { FunnelStep } from "@/lib/api";
import { nf0 } from "@/components/lab/chart";
import { formatUtc } from "@/lib/format";
import s from "./finder.module.css";

/** Last night's run, step by step. Bar lengths are on a log scale so 14 and 48,000 both show. */
export function Funnel({ steps, runAt }: { steps: FunnelStep[]; runAt: string }) {
  const max = Math.max(...steps.map((x) => x.count), 10);
  const w = (n: number) => (n <= 0 ? 0 : Math.max(2, (Math.log10(n + 1) / Math.log10(max + 1)) * 100));
  const date = formatUtc(runAt).split(",")[0];
  return (
    <figure style={{ margin: 0 }}>
      <ol className={s.funnel} aria-label={`Last night's search, ${date}`}>
        <li className={s.funnelHead}>
          <span className="label">Search of {date}</span>
          <span className="label">Count</span>
        </li>
        {steps.map((st) => (
          <li key={st.key} className={s.funnelRow}>
            <span>{st.label}</span>
            <span className={s.funnelBar} style={{ width: `${w(st.count)}%` }} aria-hidden />
            <span className={s.funnelCount}>{nf0.format(st.count)}</span>
          </li>
        ))}
        <li className={s.funnelNote}>Bar lengths use a log scale, so every step stays visible.</li>
      </ol>
    </figure>
  );
}
