"use client";

import { EXPLAIN } from "@/components/shell/explain";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCandidates, MOCK_REPLAY_OF, type CandidateList, type CandidateRow } from "@/lib/api";
import { fmtDate, fmtDepth, fmtPeriod, thousands } from "@/components/monitor/format";
import { EmptyTrace, Icon, StarGlyph, TransitGlyph } from "@/components/monitor/Glyphs";
import { PageHead } from "@/components/shell/PageHead";
import { TempKey } from "@/components/monitor/TempKey";
import { fmtSize, rowClickTarget, sizeClass, sortCandidates, DEFAULT_SORT, verdictLabel } from "./finder";
import s from "./finder.module.css";

const VOTE_WORD = { planet: "Looks like a planet", fake: "Probably not", unsure: "Not sure" } as const;

function Funnel({ list }: { list: CandidateList }) {
  return (
    <figure className={s.funnel}>
      <ol className={s.funnelRow}>
        {list.funnel.map((f) => (
          <li key={f.key} className={s.funnelStep} data-zero={f.count === 0 || undefined}>
            <span className={s.funnelNum}>{thousands(f.count)}</span>
            <span className="label">{f.label}</span>
          </li>
        ))}
      </ol>
      <figcaption className="label">What the search of {fmtDate(list.demo ? MOCK_REPLAY_OF : list.run_at)} kept at each step</figcaption>
    </figure>
  );
}

function Row({ c }: { c: CandidateRow }) {
  const href = `/candidates/${c.id}`;
  const router = useRouter();
  const onClick = (e: React.MouseEvent<HTMLTableRowElement>) => {
    const act = rowClickTarget(e, window.getSelection()?.toString() ?? "");
    if (act === "open") router.push(href);
    else if (act === "new-tab") window.open(href, "_blank", "noopener");
  };
  return (
    <tr className={s.row} onClick={onClick} data-href={href}>
      <th scope="row" className={s.cellStar}>
        <span className={s.rowStar}>
          <StarGlyph teff={c.star?.teff ?? null} radius={c.star?.rad ?? null} size={36} />
          <Link href={href} className={s.rowLink}>
            <span className={s.rowTic}>TIC {c.tic}</span>
            {c.stand_in && <span className={`${s.rowStandIn} italic`}>stand-in: {c.stand_in.name}</span>}
          </Link>
        </span>
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
      <PageHead
        title="Candidates"
        glyph={<TransitGlyph size={64} title="" />}
        items={EXPLAIN.candidates}
        facts={list ? `${list.candidates.length} shown · run ${fmtDate(list.demo ? MOCK_REPLAY_OF : list.run_at)}` : null}
      />

      {list && allStandIns && (
        <p className={s.honest}>
          <Icon name="honesty" size={24} />
          <span>
            <strong>{newCount === 0 ? "No new candidate yet." : `${newCount} new candidates.`}</strong> Below: {list.candidates.length} stand-ins, real TESS Objects of Interest.
          </span>
        </p>
      )}

      {list && (
        <div className={s.funnelRow2}>
          <Funnel list={list} />
          {allStandIns && (
            <figure className={s.emptyFig}>
              <EmptyTrace />
              <figcaption className="label">0 new candidates</figcaption>
            </figure>
          )}
        </div>
      )}

      {error && <p className="italic quiet">The candidates could not be loaded ({error}).</p>}
      {!list && !error && <div className={s.skeleton} role="status" aria-label="Loading candidates" />}
      {list && list.candidates.length === 0 && (
        <div className={s.empty}>
          <EmptyTrace />
          <p className={s.honest}>
            <Icon name="honesty" size={24} />
            <span>{list.demo ? "No candidate yet." : `No candidate yet: the search, last run ${fmtDate(list.run_at)}, has kept no signal.`}</span>
          </p>
        </div>
      )}
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
      <div className={s.afterRow}>
        <TempKey />
        <p className={s.after}>
          <Link href="/sensitivity" className={s.iconLink}>
            <Icon name="limits" size={22} />
            What it can find
          </Link>
        </p>
      </div>
    </div>
  );
}
