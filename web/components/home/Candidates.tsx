"use client";

// Home, "Candidates": the six highest-priority candidates, each as the survey picture of its star's field with the
// dip underneath. Folds come from a small precomputed file in mock mode; without it the tiles simply have no line.

import Link from "next/link";
import { useEffect, useState } from "react";
import { Picture } from "@/components/picture/Picture";
import { Sparkline } from "@/components/picture/Sparkline";
import { API_MOCK, getCandidates, type CandidateRow } from "@/lib/api";
import { starPic } from "@/lib/pictures";
import s from "./home.module.css";

type Folds = Record<string, [number, number][]>;

export function Candidates() {
  const [rows, setRows] = useState<CandidateRow[] | null>(null);
  const [folds, setFolds] = useState<Folds>({});
  useEffect(() => {
    let live = true;
    getCandidates().then(
      (l) => live && setRows([...l.candidates].sort((a, b) => b.score - a.score).slice(0, 6)),
      () => live && setRows([]),
    );
    if (API_MOCK)
      fetch("/data/finder/folds.mock.json")
        .then((r) => r.json() as Promise<{ folds: Folds }>)
        .then((f) => live && setFolds(f.folds), () => undefined);
    return () => {
      live = false;
    };
  }, []);

  return (
    <section className={`wrap ${s.sec}`} aria-labelledby="cands">
      <div className={s.shead}>
        <div>
          <h2 id="cands" className={s.h2}>
            Candidates
          </h2>
          <p className={s.line}>Dips in starlight, waiting for your eye.</p>
        </div>
        <Link href="/finder" className={s.more}>
          All candidates →
        </Link>
      </div>
      <div className={s.row6}>
        {(rows ?? Array.from({ length: 6 }, () => null)).map((c, i) => {
          if (!c) return <div key={i} className={s.skeleton} />;
          const p = starPic(c.tic);
          const name = c.name ?? `TIC ${c.tic}`;
          return (
            <figure key={c.id} className={s.cand}>
              <Link href={`/finder/${c.id}`} className={s.hit}>
                {p ? <Picture pic={p} alt={`Survey picture of the sky around ${name}; the crosshair marks the star`} sizes="(max-width: 639px) 50vw, (max-width: 1023px) 33vw, 200px" aspect="1 / 1" /> : <div className={s.skeleton} />}
                <span className={s.spark}>{folds[c.id] && <Sparkline points={folds[c.id]} label={`The dip of ${name}, folded`} />}</span>
                <span className={s.name}>{name}</span>
              </Link>
              <figcaption className="cap">{c.period_d.toFixed(2)} d · candidate</figcaption>
            </figure>
          );
        })}
      </div>
    </section>
  );
}
