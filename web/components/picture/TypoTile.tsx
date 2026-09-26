import { CategoryGlyph } from "@/components/map/CategoryGlyph";
import type { Category } from "@/lib/contract";
import s from "./picture.module.css";

/** For an event with no real picture and no precise position: its shape, its name and "TYPE · DATE". Never a stand-in image. */
export function TypoTile({ category, name, line, showName = false }: { category: Category; name: string; line: string; showName?: boolean }) {
  return (
    <div className={s.typo}>
      <CategoryGlyph category={category} size={22} />
      <div>
        <p className={s.typoName} data-show={showName || undefined}>{name}</p>
        <p className="cap">{line}</p>
      </div>
    </div>
  );
}
