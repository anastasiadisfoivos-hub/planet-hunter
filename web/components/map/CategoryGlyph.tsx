import type { Category } from "@/lib/contract";
import { CATEGORY_STYLE } from "@/lib/eventStyle";
import s from "./map.module.css";

/** The category's marker shape in its colour, as on the map. Decorative: the label says it in words. */
export function CategoryGlyph({ category, size = 12 }: { category: Category; size?: number }) {
  const st = CATEGORY_STYLE[category];
  return <span className={s.glyph} data-shape={st.shape} style={{ color: `var(${st.token})`, width: size, height: size }} aria-hidden />;
}
