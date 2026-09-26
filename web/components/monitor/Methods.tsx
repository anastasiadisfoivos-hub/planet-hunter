import Link from "next/link";
import { METHODS } from "./methodsText";
import s from "./methods.module.css";

/** The notebook: one section per step of the search, numbered in the margin in the order the search runs. */
export function Methods() {
  return (
    <div className={`wrap ${s.page}`}>
      <header className={s.head}>
        <h1>How the search works</h1>
        <p className="prose">From a star&apos;s light to a candidate, step by step, in the order the search runs.</p>
      </header>
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
            <span className={`label ${s.step}`} aria-hidden>
              {String(i + 1).padStart(2, "0")}
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
                <p className={`${s.pending} italic`}>Written by the methods session; not yet here.</p>
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
