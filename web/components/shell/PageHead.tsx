import { Explainer, type ExplainItem } from "./Explainer";
import s from "./pagehead.module.css";

/**
 * Every page's head (DESIGN.md v3: Space and grid): the title in the left 5 of 12 columns, the explainer strip and
 * one mono line of facts in the right 7, over a 2px ink rule with a tick at each end.
 */
export function PageHead({ title, kicker, glyph, items, facts, children }: { title: string; kicker?: string; glyph?: React.ReactNode; items: ExplainItem[]; facts?: string | null; children?: React.ReactNode }) {
  return (
    <header className={s.head}>
      <div className={s.titleCol}>
        {glyph && <span className={s.glyph}>{glyph}</span>}
        <h1 className={s.title}>
          {kicker && <span className={s.kicker}>{kicker}</span>}
          {title}
        </h1>
      </div>
      <div className={s.side}>
        <Explainer items={items} />
        {facts && <p className="label">{facts}</p>}
        {children}
      </div>
    </header>
  );
}
