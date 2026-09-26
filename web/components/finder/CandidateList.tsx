"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { DownloadSimple, FadersHorizontal } from "@phosphor-icons/react";
import { Button, DemoTag, EmptyState } from "@/components/ui";
import { LoadError } from "@/components/lab/chart";
import { API_MOCK, exportCtoiCsv, getCandidates, type CandidateList as List, type CandidateRow, type PixelVerdict } from "@/lib/api";
import {
  activeFilterCount,
  DEFAULT_SORT,
  filterCandidates,
  fmtPeriod,
  NO_FILTERS,
  PERIOD_RANGES,
  rEarth,
  SIZE_RANGES,
  SORTS,
  sortCandidates,
  VERDICTS,
  type Filters,
  type Sort,
  type SortKey,
} from "./finder";
import { Funnel } from "./Funnel";
import { Drawer } from "@/components/picture/Drawer";
import { Info } from "@/components/picture/Info";
import { Picture } from "@/components/picture/Picture";
import { Sparkline } from "@/components/picture/Sparkline";
import { honesty, starPic } from "@/lib/pictures";
import g from "./grid.module.css";
import s from "./finder.module.css";

const title = (c: CandidateRow) => `TIC ${c.tic}`;

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

type Folds = Record<string, [number, number][]>;

export function CandidateList() {
  const admin = useSearchParams().get("admin");
  const [data, setData] = useState<List | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [folds, setFolds] = useState<Folds>({});

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

  // Mock mode: a tiny binned fold per candidate, so each tile can draw its dip without the full light curve.
  useEffect(() => {
    if (!API_MOCK) return;
    fetch("/data/finder/folds.mock.json")
      .then((r) => r.json() as Promise<{ folds: Folds }>)
      .then((f) => setFolds(f.folds), () => undefined);
  }, []);

  const rows = useMemo(() => (data ? sortCandidates(filterCandidates(data.candidates, filters), sort) : []), [data, filters, sort]);
  const pick = (id: string) => setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const nActive = activeFilterCount(filters);
  const funnel = data?.funnel ?? [];
  const searched = funnel[0]?.count;
  const review = funnel.at(-1)?.count;

  if (error) return <LoadError what="The candidate list" error={error} onRetry={() => setAttempt((n) => n + 1)} />;

  return (
    <>
      <div className={g.head}>
        <div>
          <h1 className={g.h1}>Candidates</h1>
          <p className={g.line}>Dips in starlight, waiting for your eye.</p>
        </div>
        {data?.demo && <DemoTag />}
      </div>

      <div className={g.bar}>
        <span className="cap">
          {searched != null && review != null ? (
            <>
              {searched.toLocaleString("en-US")} stars searched → {review} to review
            </>
          ) : (
            " "
          )}
        </span>
        <div className={g.tools}>
          <label className={g.sort}>
            <span className="sr-only">Sort by</span>
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
          <Button icon={<FadersHorizontal size={16} aria-hidden />} aria-expanded={open} aria-controls="finder-filters" onClick={() => setOpen((o) => !o)}>
            {nActive ? `Filter (${nActive})` : "Filter"}
          </Button>
        </div>
      </div>

      {admin && <AdminBar token={admin} selected={selected} clear={() => setSelected([])} />}
      <FiltersBar f={filters} set={setFilters} open={open} shown={rows.length} total={data?.candidates.length ?? 0} />

      {!data ? (
        <div className={g.grid} role="status" aria-busy="true">
          <span className="sr-only">Loading candidates</span>
          {Array.from({ length: 10 }, (_, i) => (
            <div key={i} className={g.skeleton} />
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
        <ul className={g.grid}>
          {rows.map((c) => {
            const p = starPic(c.tic);
            const name = c.name ?? title(c);
            return (
              <li key={c.id} className={g.tile} data-selected={selected.includes(c.id) || undefined}>
                <Link href={`/finder/${c.id}`} className={g.hit}>
                  {p ? <Picture pic={p} alt={`Survey picture of the sky around ${name}; the crosshair marks the star`} sizes="(max-width: 639px) 50vw, (max-width: 1023px) 33vw, 262px" aspect="1 / 1" /> : <div className={g.skeleton} />}
                  <span className={g.spark}>{folds[c.id] && <Sparkline points={folds[c.id]} label={`The dip of ${name}, folded on its period`} />}</span>
                  <span className={g.name}>{name}</span>
                </Link>
                <div className={g.capline}>
                  <span className="cap">
                    {fmtPeriod(c.period_d)} · priority {c.score.toFixed(2)}
                  </span>
                  {p && <Info pic={p} note={`${honesty(null, p)} Size: ${rEarth(c.radius_rjup).toFixed(1)} × Earth.`} />}
                </div>
                {admin && (
                  <label className={g.pick}>
                    <input type="checkbox" className={s.check} checked={selected.includes(c.id)} onChange={() => pick(c.id)} />
                    Select for export
                  </label>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <section className={g.more} aria-label="About the search">
        <Drawer title="How the search narrows" state={review != null ? `${review} to review` : undefined}>
          {data ? <Funnel steps={data.funnel} runAt={data.run_at} /> : null}
        </Drawer>
        <Drawer title="What it can find" state="Sensitivity">
          <p>Which planet sizes and orbits the nightly search recovers, measured by hiding simulated planets in real TESS light curves.</p>
          <p>
            <Link href="/finder/sensitivity">See what the search can find</Link>
          </p>
        </Drawer>
        <Drawer title="What a candidate is" state="About">
          <p>A repeating dip in a star&apos;s light that passed our checks and is on none of the lists we compared. None of them is a planet yet. Priority is a machine ranking from 0 to 1 that orders the list; it is not the chance a planet is real.</p>
          {data?.demo && <p>Demo data: these candidates are made up and their light curves simulated, to show how a report reads. Their sky pictures are real survey pictures of each star.</p>}
        </Drawer>
      </section>
    </>
  );
}
