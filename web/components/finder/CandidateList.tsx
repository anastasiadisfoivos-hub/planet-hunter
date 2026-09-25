"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, DownloadSimple, FadersHorizontal } from "@phosphor-icons/react";
import { Button, DemoTag, EmptyState } from "@/components/ui";
import { LoadError } from "@/components/lab/chart";
import { exportCtoiCsv, getCandidates, type CandidateList as List, type CandidateRow, type PixelVerdict } from "@/lib/api";
import {
  activeFilterCount,
  DEFAULT_SORT,
  filterCandidates,
  fmtPeriod,
  fmtSize,
  NEEDS_VOTES_BELOW,
  nextSort,
  NO_FILTERS,
  PERIOD_RANGES,
  SIZE_RANGES,
  sizeClass,
  SORTS,
  sortCandidates,
  totalVotes,
  VERDICTS,
  type Filters,
  type Sort,
  type SortKey,
} from "./finder";
import { Funnel } from "./Funnel";
import { VerdictBadge } from "./Verdict";
import { formatDay } from "@/lib/format";
import s from "./finder.module.css";
import l from "@/components/lab/lab.module.css";

const fmtDate = (iso: string) => formatDay(iso, Date.now());
const title = (c: CandidateRow) => `TIC ${c.tic}`;

function ScoreCell({ c }: { c: CandidateRow }) {
  const parts = Object.values(c.score_parts);
  return (
    <span className={s.score} title="Machine ranking, 0 to 1. Open the report for its parts.">
      <span className={s.num}>{c.score.toFixed(2)}</span>
      <span className={s.scoreBar} aria-hidden>
        {parts.map((p, i) => (
          <span key={i} style={{ width: `${p * 64}px` }} />
        ))}
      </span>
    </span>
  );
}

function VotesCell({ c }: { c: CandidateRow }) {
  const n = totalVotes(c.votes);
  if (n === 0) return <span className={s.needs}>No votes yet</span>;
  const w = (k: number) => `${(k / n) * 100}%`;
  return (
    <span className={s.votesMini} aria-label={`${c.votes.planet} planet, ${c.votes.fake} fake, ${c.votes.unsure} not sure`}>
      <span className={s.num}>
        {n}
        {n < NEEDS_VOTES_BELOW && <span className={s.needs}> · needs votes</span>}
      </span>
      <span className={s.votesBar} aria-hidden>
        <span className={s.vPlanet} style={{ width: w(c.votes.planet) }} />
        <span className={s.vFake} style={{ width: w(c.votes.fake) }} />
        <span className={s.vUnsure} style={{ width: w(c.votes.unsure) }} />
      </span>
    </span>
  );
}

function SortHeader({ k, sort, onSort, children, right }: { k: SortKey; sort: Sort; onSort: (k: SortKey) => void; children: ReactNode; right?: boolean }) {
  const active = sort.key === k;
  return (
    <th className={right ? s.right : undefined} aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className={s.sortButton} data-active={active} onClick={() => onSort(k)}>
        {children}
        {active && (sort.dir === "asc" ? <ArrowUp size={11} weight="bold" aria-hidden /> : <ArrowDown size={11} weight="bold" aria-hidden />)}
      </button>
    </th>
  );
}

function FiltersBar({ f, set, open, shown, total }: { f: Filters; set: (f: Filters) => void; open: boolean; shown: number; total: number }) {
  const toggle = (v: PixelVerdict) => set({ ...f, verdicts: f.verdicts.includes(v) ? f.verdicts.filter((x) => x !== v) : [...f.verdicts, v] });
  return (
    <div className={s.filters} data-open={open} id="finder-filters">
      <label className={s.field}>
        <span className="label">Size</span>
        <select className={s.select} value={f.size} onChange={(e) => set({ ...f, size: e.target.value })}>
          {SIZE_RANGES.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      <label className={s.field}>
        <span className="label">Period</span>
        <select className={s.select} value={f.period} onChange={(e) => set({ ...f, period: e.target.value })}>
          {PERIOD_RANGES.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      <fieldset className={s.field} style={{ border: 0, margin: 0, padding: 0 }}>
        <legend className="label" style={{ marginBottom: 6, padding: 0 }}>
          Pixel check
        </legend>
        <div className={s.chips}>
          {VERDICTS.map((v) => (
            <button key={v.value} type="button" className={s.chip} aria-pressed={f.verdicts.includes(v.value)} onClick={() => toggle(v.value)}>
              {v.label}
            </button>
          ))}
        </div>
      </fieldset>
      <div className={s.field}>
        <span className="label" aria-hidden>
          Votes
        </span>
        <button type="button" className={s.chip} aria-pressed={f.needsVotes} onClick={() => set({ ...f, needsVotes: !f.needsVotes })}>
          Needs votes
        </button>
      </div>
      <div className={s.filterMeta} role="status">
        <span>
          <span className={s.num}>{shown}</span> of <span className={s.num}>{total}</span>
        </span>
        {activeFilterCount(f) > 0 && (
          <Button size="sm" variant="quiet" onClick={() => set(NO_FILTERS)}>
            Clear filters
          </Button>
        )}
      </div>
    </div>
  );
}

function AdminBar({ token, selected, clear }: { token: string; selected: string[]; clear: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const { filename, csv } = await exportCtoiCsv(selected, token);
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: filename });
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={s.adminBar} role="region" aria-label="Admin">
      <span className="label">Admin</span>
      <p>
        <span className={s.num}>{selected.length}</span> selected. The API checks the admin token before exporting; the demo builds the file here and sends
        nothing.
      </p>
      {selected.length > 0 && (
        <Button size="sm" variant="quiet" onClick={clear}>
          Clear selection
        </Button>
      )}
      <Button variant="primary" icon={<DownloadSimple size={14} aria-hidden />} disabled={!selected.length || busy} onClick={run}>
        {busy ? "Building file" : "Export selected as ExoFOP CTOI CSV"}
      </Button>
      {error && (
        <p className={s.adminError} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function CandidateList() {
  const admin = useSearchParams().get("admin");
  const [data, setData] = useState<List | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    const ctl = new AbortController();
    getCandidates(ctl.signal)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => !ctl.signal.aborted && setError(e instanceof Error ? e.message : String(e)));
    return () => ctl.abort();
  }, [attempt]);

  const rows = useMemo(() => (data ? sortCandidates(filterCandidates(data.candidates, filters), sort) : []), [data, filters, sort]);
  const onSort = useCallback((k: SortKey) => setSort((cur) => nextSort(cur, k)), []);
  const pick = (id: string) => setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const nActive = activeFilterCount(filters);

  if (error) return <LoadError what="The candidate list" error={error} onRetry={() => setAttempt((n) => n + 1)} />;

  return (
    <>
      <div className={s.top}>
        <div className={s.introText}>
          <div className={l.titleRow}>
            <h1 className={l.h1}>Planet candidates</h1>
            {data?.demo && <DemoTag />}
          </div>
          <ul className={s.introLines}>
            <li>
              Every night we search TESS light curves for <strong>small, repeating dips</strong> in a star&apos;s brightness, the mark a planet leaves as it crosses its star.
            </li>
            <li>Most dips are not planets. Each signal here passed our checks and is <strong>not on the lists we checked</strong>.</li>
            <li>They are <strong>candidates</strong>, not planets. Look at the evidence and tell us what you think.</li>
          </ul>
        </div>
        {data ? <Funnel steps={data.funnel} runAt={data.run_at} /> : <div className={l.skeleton} style={{ height: 260 }} role="status" aria-label="Loading the search summary" />}
      </div>

      <section className={s.section} aria-labelledby="list-h">
        <div className={s.listHead}>
          <h2 id="list-h" className={l.h2}>
            Ranked by score
          </h2>
          <div className={s.filterToggle}>
            <Button icon={<FadersHorizontal size={16} aria-hidden />} aria-expanded={open} aria-controls="finder-filters" onClick={() => setOpen((o) => !o)}>
              {nActive ? `Filters (${nActive})` : "Filters"}
            </Button>
          </div>
        </div>
        <p className={s.sectionLede}>The score is a machine ranking from 0 to 1, built from four parts shown in each report. It is not a probability that the planet is real.</p>

        {admin && <AdminBar token={admin} selected={selected} clear={() => setSelected([])} />}

        <FiltersBar f={filters} set={setFilters} open={open} shown={rows.length} total={data?.candidates.length ?? 0} />

        <label className={`${s.field} ${s.mobileSort}`}>
          <span className="label">Sort by</span>
          <select
            className={s.select}
            value={`${sort.key}:${sort.dir}`}
            onChange={(e) => {
              const [key, dir] = e.target.value.split(":") as [SortKey, "asc" | "desc"];
              setSort({ key, dir });
            }}
          >
            {SORTS.flatMap((o) => [
              <option key={`${o.key}:desc`} value={`${o.key}:desc`}>
                {o.label}, {o.key === "created" ? "newest first" : "highest first"}
              </option>,
              <option key={`${o.key}:asc`} value={`${o.key}:asc`}>
                {o.label}, {o.key === "created" ? "oldest first" : "lowest first"}
              </option>,
            ])}
          </select>
        </label>

        {!data ? (
          <div className={s.skeletonRows} role="status" aria-busy="true">
            <span className="sr-only">Loading candidates</span>
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className={s.skeletonRow} />
            ))}
          </div>
        ) : data.candidates.length === 0 ? (
          <EmptyState title="No candidates from the latest search">
            Nothing from the last run got through the checks and the known-list comparison. The next search runs tonight.
          </EmptyState>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No candidates match these filters"
            action={
              <Button variant="primary" onClick={() => setFilters(NO_FILTERS)}>
                Clear filters
              </Button>
            }
          >
            Try a wider size or period range, or another pixel verdict.
          </EmptyState>
        ) : (
          <>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <caption className="sr-only">Planet candidates, {rows.length} shown. Column headers sort the table.</caption>
                <thead>
                  <tr>
                    {admin && (
                      <th>
                        <span className="sr-only">Select</span>
                      </th>
                    )}
                    <th>
                      <span className="label">Candidate</span>
                    </th>
                    <SortHeader k="score" sort={sort} onSort={onSort} right>
                      Score
                    </SortHeader>
                    <SortHeader k="period" sort={sort} onSort={onSort} right>
                      Period
                    </SortHeader>
                    <SortHeader k="size" sort={sort} onSort={onSort}>
                      Size
                    </SortHeader>
                    <th>
                      <span className="label">Pixel check</span>
                    </th>
                    <SortHeader k="votes" sort={sort} onSort={onSort} right>
                      Votes
                    </SortHeader>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.id} className={s.row} data-selected={selected.includes(c.id)}>
                      {admin && (
                        <td>
                          <input type="checkbox" className={s.check} checked={selected.includes(c.id)} onChange={() => pick(c.id)} aria-label={`Select ${title(c)}`} />
                        </td>
                      )}
                      <td>
                        <span className={s.cellStack}>
                          <Link href={`/finder/${c.id}`} className={s.rowLink}>
                            {title(c)}
                          </Link>
                          <span className={s.cellSub}>
                            {c.name ? `${c.name}, ` : ""}found {fmtDate(c.created_at)}
                          </span>
                        </span>
                      </td>
                      <td className={s.right}>
                        <ScoreCell c={c} />
                      </td>
                      <td className={`${s.right} ${s.num}`}>{fmtPeriod(c.period_d)}</td>
                      <td>
                        <span className={s.cellStack}>
                          <span className={s.num}>{fmtSize(c.radius_rjup)}</span>
                          <span className={s.cellSub}>{sizeClass(c.radius_rjup)}</span>
                        </span>
                      </td>
                      <td>
                        <VerdictBadge verdict={c.pixel_verdict} />
                      </td>
                      <td className={s.right}>
                        <VotesCell c={c} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className={s.cards}>
              {rows.map((c) => (
                <li key={c.id} className={`${s.card} ${s.row}`} data-selected={selected.includes(c.id)}>
                  <div className={s.cardTop}>
                    <span className={s.cellStack}>
                      <Link href={`/finder/${c.id}`} className={s.rowLink}>
                        {title(c)}
                      </Link>
                      <span className={s.cellSub}>
                        {c.name ? `${c.name}, ` : ""}
                        {sizeClass(c.radius_rjup)}
                      </span>
                    </span>
                    <VerdictBadge verdict={c.pixel_verdict} />
                  </div>
                  <dl className={s.cardFacts}>
                    <div>
                      <dt className="label">Score</dt>
                      <dd>{c.score.toFixed(2)}</dd>
                    </div>
                    <div>
                      <dt className="label">Period</dt>
                      <dd>{fmtPeriod(c.period_d)}</dd>
                    </div>
                    <div>
                      <dt className="label">Size</dt>
                      <dd>{fmtSize(c.radius_rjup).replace(" × ", "× ")}</dd>
                    </div>
                    <div>
                      <dt className="label">Votes</dt>
                      <dd>{totalVotes(c.votes)}</dd>
                    </div>
                  </dl>
                  {admin && (
                    <label className={s.cardCheck}>
                      <input type="checkbox" className={s.check} checked={selected.includes(c.id)} onChange={() => pick(c.id)} />
                      Select for export
                    </label>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      {data?.demo && (
        <p className={`${l.help} ${l.footnote}`}>
          Demo data: these candidates are made up and their light curves simulated, to show how a report reads. The pixel images are borrowed from real pixel checks
          of WASP-18 and TOI-4257. Real candidates arrive when the Finder service is connected.
        </p>
      )}
    </>
  );
}
