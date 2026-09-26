"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getCandidates, MOCK_REPLAY_OF, type CandidateList, type CandidateRow } from "@/lib/api";
import { fmtDate, fmtDepth, fmtPeriod, thousands } from "@/components/monitor/format";
import { fmtSize, sizeClass, sortCandidates, DEFAULT_SORT, verdictLabel } from "./finder";
import s from "./finder.module.css";

const VOTE_WORD = { planet: "Looks like a planet", fake: "Probably not", unsure: "Not sure" } as const;

function Funnel({ list }: { list: CandidateList }) {
  return (
    <figure className={s.funnel}>
      <ol className={s.funnelRow}>
        {list.funnel.map((f, i) => (
          <li key={f.key} className={s.funnelStep} data-zero={f.count === 0 || undefined}>
            <span className={s.funnelNum}>{thousands(f.count)}</span>
            <span className="label">{f.label}</span>
            {i < list.funnel.length - 1 && <span className={s.funnelArrow} aria-hidden />}
          </li>
        ))}
      </ol>
      <figcaption className="label">What the search of {fmtDate(list.demo ? MOCK_REPLAY_OF : list.run_at)} kept at each step</figcaption>
    </figure>
  );
}

function Row({ c }: { c: CandidateRow }) {
  const href = `/candidates/${c.id}`;
  return (
    <tr className={s.row}>
      <th scope="row" className={s.cellStar}>
        <Link href={href} className={s.rowLink}>
          <span className={s.rowTic}>TIC {c.tic}</span>
          {c.stand_in && <span className={`${s.rowStandIn} italic`}>stand-in: {c.stand_in.name}</span>}
        </Link>
      </th>
      <td className="num" data-label="Period">
        {fmtPeriod(c.period_d)}
      </td>
      <td className="num" data-label="Depth">
        {fmtDepth(c.depth_ppm)}
      </td>
      <td data-label="Size">
        <span className="num">{fmtSize(c.radius_rjup)}</span>
        <span className={s.sub}>{sizeClass(c.radius_rjup)}</span>
      </td>
      <td className="num" data-label="Checks">
        {c.checks_passed} of {c.checks_total}
      </td>
      <td data-label="Pixel check">{verdictLabel(c.pixel_verdict)}</td>
      <td data-label="Vetting" className={s.cellVerdict} data-verdict={c.verdict ?? undefined}>
        {c.verdict ?? "not vetted yet"}
      </td>
      <td data-label="Your vote" className={s.voteCell}>
        {c.votes.my_vote ? VOTE_WORD[c.votes.my_vote] : "not voted"}
      </td>
    </tr>
  );
}

export function CandidateTable() {
  const [list, setList] = useState<CandidateList | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const ac = new AbortController();
    getCandidates(ac.signal)
      .then(setList)
      .catch((e: unknown) => !ac.signal.aborted && setError(e instanceof Error ? e.message : String(e)));
    return () => ac.abort();
  }, []);

  const allStandIns = !!list && list.candidates.length > 0 && list.candidates.every((c) => c.stand_in);
  const newCount = list?.funnel.find((f) => f.key === "candidates")?.count ?? null;
  return (
    <div className={`wrap ${s.page}`}>
      <header className={s.pageHead}>
        <h1>Candidates</h1>
        <div className={`prose ${s.lead}`}>
          {list && allStandIns ? (
            <p>
              The search has found <strong>{newCount === 0 ? "no new candidate" : `${newCount} new candidates`}</strong> yet. The {list.candidates.length} below are
              stand-ins: real TESS Objects of Interest, searched again with the lists of known objects switched off, so each dossier shows a real signal.
            </p>
          ) : (
            <p>Signals that passed every check and are on none of the lists we checked. Each is a candidate, not a confirmed planet.</p>
          )}
          <p className="quiet">A candidate is a dip that passed every check. It is not a confirmed planet until astronomers follow it up.</p>
        </div>
      </header>

      {list && <Funnel list={list} />}

      {error && <p className="italic quiet">The candidates could not be loaded ({error}).</p>}
      {!list && !error && <div className={s.skeleton} role="status" aria-label="Loading candidates" />}
      {list && list.candidates.length === 0 && <p className="italic quiet">No candidates yet. When the search keeps a signal, it appears here.</p>}
      {list && list.candidates.length > 0 && (
        <table className={s.table}>
          <caption className="sr-only">Planet candidates and stand-ins, highest priority first</caption>
          <thead>
            <tr>
              <th scope="col" className="label">Star</th>
              <th scope="col" className="label">Period</th>
              <th scope="col" className="label">Depth</th>
              <th scope="col" className="label">Size</th>
              <th scope="col" className="label">Checks</th>
              <th scope="col" className="label">Pixel check</th>
              <th scope="col" className="label">Vetting</th>
              <th scope="col" className="label">Your vote</th>
            </tr>
          </thead>
          <tbody>
            {sortCandidates(list.candidates, DEFAULT_SORT).map((c) => (
              <Row key={c.id} c={c} />
            ))}
          </tbody>
        </table>
      )}
      <p className={s.after}>
        <Link href="/sensitivity">What the search can and cannot find</Link>
      </p>
    </div>
  );
}
