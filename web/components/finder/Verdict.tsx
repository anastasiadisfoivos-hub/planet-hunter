import { CheckCircle, Question, WarningCircle, XCircle, CircleDashed } from "@phosphor-icons/react/dist/ssr";
import type { PixelVerdict } from "@/lib/api";
import { verdictLabel } from "./finder";
import s from "./finder.module.css";

const ICON = {
  "on target": CheckCircle,
  "possible neighbour": WarningCircle,
  "off target": XCircle,
  inconclusive: Question,
} as const;

/** The pixel check's verdict: a data colour plus its own shape, never colour alone. */
export function VerdictBadge({ verdict }: { verdict: PixelVerdict | null }) {
  const Icon = verdict ? ICON[verdict] : CircleDashed;
  return (
    <span className={s.verdict} data-v={verdict ?? "none"}>
      <Icon size={14} weight="bold" aria-hidden />
      <span>{verdictLabel(verdict)}</span>
    </span>
  );
}
