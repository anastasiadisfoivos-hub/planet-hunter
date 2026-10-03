import { EXPLAIN } from "@/components/shell/explain";
import Link from "next/link";
import { PageHead } from "@/components/shell/PageHead";
import { Icon } from "./Glyphs";
import { METHODS } from "./methodsText";
import s from "./methods.module.css";

/** The notebook: one section per step of the search, numbered in the margin in the order the search runs. */
export function Methods() {
  return (
    <div className={`wrap ${s.page}`}>
      <div className={s.headRow}>
        <PageHead
          title="Methods"
          items={EXPLAIN.methods}
        />
      </div>
      <nav aria-label="On this page" className={s.toc}>
        <ol>
          {METHODS.map((m) => (
            <li key={m.id}>
              <a href={`#${m.id}`}>{m.title}</a>
            </li>
          ))}
        </ol>
      </nav>
      <ol className={s.sections}>
        {METHODS.map((m, i) => (
          <li key={m.id} className={s.section}>
            <span className={s.step} aria-hidden>
              <span className="label">{String(i + 1).padStart(2, "0")}</span>
              <Icon name={m.icon} size={28} />
            </span>
            <section aria-labelledby={m.id} className={s.body}>
              <h2 id={m.id}>{m.title}</h2>
              <p className={s.asks}>{m.asks}</p>
              {m.body.length ? (
                <div className="prose">
                  {m.body.map((p) => (
                    <p key={p}>{p}</p>
                  ))}
                </div>
              ) : (
                <p className={s.pending}>Text to come from the methods session.</p>
              )}
              {m.link && (
                <p>
                  <Link href={m.link.href}>{m.link.text}</Link>
                </p>
              )}
            </section>
          </li>
        ))}
      </ol>
    </div>
  );
}
