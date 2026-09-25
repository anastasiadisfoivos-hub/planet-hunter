"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, ArrowSquareOut, CheckCircle, MinusCircle, XCircle } from "@phosphor-icons/react";
import { DemoTag, EmptyState } from "@/components/ui";
import { LoadError } from "@/components/lab/chart";
import { ApiError, getCandidate, getMapHostTics, type Candidate, type CandidateReport } from "@/lib/api";
import {
  BTJD_TO_BJD,
  checkLabel,
  fmtCheckValue,
  fmtDepth,
  fmtPeriod,
  KNOWN_LISTS,
  listMatch,
  partLabel,
  rEarth,
  SCORE_PARTS,
  sizeClass,
} from "./finder";
import { FoldedCurve, UnfoldedCurve } from "./LightCurves";
import { PixelCheck } from "./Pixels";
import { VoteBox } from "./VoteBox";
import { formatUtc } from "@/lib/format";
import s from "./finder.module.css";
import l from "@/components/lab/lab.module.css";

const fmtDay = (iso: string) => formatUtc(iso).split(",")[0];
const PART_COLORS = ["var(--ink)", "var(--ink-secondary)", "var(--ink-muted)", "var(--ink-faint)"];

function Header({ c, demo, onMap }: { c: Candidate; demo: boolean; onMap: boolean | null }) {
  const re = rEarth(c.radius_rjup);
  const disabled = onMap === false;
  return (
    <header className={s.head}>
      <div className={s.headTop}>
        <div className={s.headTitle}>
          <span className="label">Planet candidate</span>
          <div className={l.titleRow}>
            <h1 className={l.h1}>TIC {c.tic}</h1>
            {demo && <DemoTag />}
          </div>
          <p className={l.lede}>
            {c.name ? `Around ${c.name}, a known planet host: a new signal that matches none of its listed planets. ` : ""}
            Found {fmtDay(c.created_at)} in TESS sector{c.sectors.length > 1 ? "s" : ""} {c.sectors.join(", ")}.
          </p>
        </div>
        <div className={s.headActions}>
          <Link className={s.ghostLink} href={`/lab/star/${c.tic}`} aria-disabled={disabled || undefined} tabIndex={disabled ? -1 : undefined}>
            Open star lab
          </Link>
          <Link className={s.ghostLink} href={`/map?host=${c.tic}`} aria-disabled={disabled || undefined} tabIndex={disabled ? -1 : undefined}>
            Fly to it
            <ArrowRight size={14} aria-hidden />
          </Link>
        </div>
      </div>
      {disabled && <p className={s.hostNote}>This star isn&apos;t on the sky map yet (the map shows known planet hosts), so it has no star lab or flight.</p>}
      <dl className={s.facts}>
        <div>
          <dt className="label">Period</dt>
          <dd>
            {fmtPeriod(c.period_d)}
            <span className={s.factNote}>{c.period_d.toFixed(5)} days</span>
          </dd>
        </div>
        <div>
          <dt className="label">Size</dt>
          <dd>
            {re.toFixed(1)} × Earth
            <span className={s.factNote}>
              likely {rEarth(c.radius_low).toFixed(1)} to {rEarth(c.radius_high).toFixed(1)}, {sizeClass(c.radius_rjup)}
            </span>
          </dd>
        </div>
        <div>
          <dt className="label">Dip depth</dt>
          <dd>
            {fmtDepth(c.depth_ppm)}
            <span className={s.factNote}>{Math.round(c.depth_ppm)} ppm of the starlight</span>
          </dd>
        </div>
        <div>
          <dt className="label">Dip length</dt>
          <dd>
            {c.duration_h.toFixed(1)} h<span className={s.factNote}>{c.n_transits} dips seen</span>
          </dd>
        </div>
        <div>
          <dt className="label">Signal</dt>
          <dd>
            SNR {c.snr.toFixed(1)}
            <span className={s.factNote}>SDE {c.sde.toFixed(1)}</span>
          </dd>
        </div>
        <div>
          <dt className="label">First dip</dt>
          <dd>
            {c.t0_btjd.toFixed(4)}
            <span className={s.factNote}>BTJD, or BJD {(c.t0_btjd + BTJD_TO_BJD).toFixed(4)}</span>
          </dd>
        </div>
        <div>
          <dt className="label">Checks</dt>
          <dd>
            {c.checks.filter((k) => k.passed === true).length} of {c.checks.length}
            <span className={s.factNote}>passed</span>
          </dd>
        </div>
        <div>
          <dt className="label">Score</dt>
          <dd>
            {c.score.toFixed(2)}
            <span className={s.factNote}>machine ranking, 0 to 1</span>
          </dd>
        </div>
      </dl>
    </header>
  );
}

function Checks({ c }: { c: Candidate }) {
  const failed = c.checks.filter((k) => k.passed === false).length;
  const skipped = c.checks.filter((k) => k.passed == null).length;
  return (
    <section className={s.section} aria-labelledby="checks-h">
      <div className={s.sectionHead}>
        <h2 id="checks-h" className={l.h2}>
          Checks
        </h2>
        <span className="label">
          {c.checks.length - failed - skipped} passed
          {failed ? `, ${failed} failed` : ""}
          {skipped ? `, ${skipped} couldn't run` : ""}
        </span>
      </div>
      <p className={s.sectionLede}>Tests that catch the usual fakes: noise, two stars eclipsing each other, and light from a neighbour. Every test is listed, passed or not.</p>
      <ul className={s.checkList}>
        {c.checks.map((k) => {
          const st = k.passed === true ? "pass" : k.passed === false ? "fail" : "skip";
          const Icon = st === "pass" ? CheckCircle : st === "fail" ? XCircle : MinusCircle;
          return (
            <li key={k.name} className={s.checkRow} data-state={st}>
              <Icon className={s.checkIcon} data-state={st} size={18} weight="bold" aria-hidden />
              <span className={s.checkName}>
                {checkLabel(k.name)}
                <span className={s.checkState}>{st === "pass" ? "Passed" : st === "fail" ? "Failed" : "Couldn't run"}</span>
              </span>
              <span className={s.checkValue}>{fmtCheckValue(k.name, k.value)}</span>
              <p className={s.checkReason}>{k.reason}</p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function KnownLists({ c }: { c: Candidate }) {
  return (
    <section className={s.section} aria-labelledby="lists-h">
      <div className={s.sectionHead}>
        <h2 id="lists-h" className={l.h2}>
          Known lists
        </h2>
      </div>
      <p className={s.sectionLede}>
        The signal was compared by star and period with the lists below. &quot;Not on the list&quot; means no match in the copy we checked; it can still be known somewhere
        else.
      </p>
      <ul className={s.lists}>
        {KNOWN_LISTS.map((k) => {
          const m = listMatch(c.known_lists[k.key]);
          return (
            <li key={k.key} className={s.listItem} data-matched={m.matched}>
              <span className="label">{k.label}</span>
              <span className={s.listResult}>
                {m.matched ? <XCircle size={16} weight="bold" aria-hidden /> : <MinusCircle size={16} aria-hidden />}
                {m.matched ? `On the list${m.id ? `: ${m.id}` : ""}` : "Not on the list"}
              </span>
              <a className={s.listSource} href={k.url} target="_blank" rel="noreferrer">
                {k.source}
              </a>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Score({ c }: { c: Candidate }) {
  const parts = Object.entries(c.score_parts);
  return (
    <section className={s.section} aria-labelledby="score-h">
      <div className={s.sectionHead}>
        <h2 id="score-h" className={l.h2}>
          Score
        </h2>
      </div>
      <div className={s.scoreHead}>
        <span className={s.scoreBig}>{c.score.toFixed(2)}</span>
        <span className={s.muted}>of 1, a machine ranking. It orders the list; it is not the chance this is a planet.</span>
      </div>
      <div className={s.stack} role="img" aria-label={parts.map(([k, v]) => `${partLabel(k)} ${v.toFixed(2)}`).join(", ")}>
        {parts.map(([k, v], i) => (
          <span key={k} style={{ width: `${v * 100}%`, background: PART_COLORS[i % PART_COLORS.length] }} />
        ))}
      </div>
      <ul className={s.parts}>
        {parts.map(([k, v], i) => (
          <li key={k} className={s.part}>
            <span className={s.partSwatch} style={{ background: PART_COLORS[i % PART_COLORS.length] }} aria-hidden />
            <span className={s.partName}>{partLabel(k)}</span>
            <span className={s.num}>+{v.toFixed(2)}</span>
            <span>{SCORE_PARTS[k]?.text ?? ""}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Footer({ c }: { c: Candidate }) {
  return (
    <section className={s.section} aria-labelledby="about-h">
      <h2 id="about-h" className="sr-only">
        About candidates
      </h2>
      <div className={s.footer}>
        <div>
          <h3>What a candidate is</h3>
          <p>
            A repeating dip in a star&apos;s light that passed our checks and isn&apos;t on the lists we compared it with. Many candidates turn out to be eclipsing
            stars, a blended neighbour or an instrument effect. None of them is a planet yet.
          </p>
        </div>
        <div>
          <h3>What confirmation needs</h3>
          <p>
            Follow-up by professionals: sharper images to rule out neighbours, more dips from the ground, and usually the star&apos;s wobble measured with a
            spectrograph to weigh the companion. That takes months to years.
          </p>
        </div>
        <div>
          <h3>ExoFOP</h3>
          <p>
            Strong candidates can be posted to{" "}
            <a href={`https://exofop.ipac.caltech.edu/tess/target.php?id=${c.tic}`} target="_blank" rel="noreferrer">
              ExoFOP <ArrowSquareOut size={12} aria-hidden style={{ verticalAlign: "-1px" }} />
            </a>
            , where TESS follow-up teams share observations, as a Community TOI. Posting is a review step, not a claim.
          </p>
        </div>
      </div>
    </section>
  );
}

export function Report({ id }: { id: string }) {
  const [r, setR] = useState<CandidateReport | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [hosts, setHosts] = useState<Set<number> | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    getCandidate(id, ctl.signal)
      .then((v) => {
        setR(v);
        setError(null);
      })
      .catch((e: unknown) => !ctl.signal.aborted && setError({ status: e instanceof ApiError ? e.status : 0, message: e instanceof Error ? e.message : String(e) }));
    return () => ctl.abort();
  }, [id, attempt]);

  useEffect(() => {
    getMapHostTics()
      .then(setHosts)
      .catch(() => setHosts(null));
  }, []);

  const back = (
    <Link href="/finder" className={s.quietLink}>
      <ArrowLeft size={14} aria-hidden />
      All candidates
    </Link>
  );

  if (error) {
    return error.status === 404 ? (
      <>
        <div className={s.back}>{back}</div>
        <EmptyState
          title="No candidate with that name"
          action={
            <Link href="/finder" className={s.ghostLink}>
              See all candidates
            </Link>
          }
        >
          It may have been withdrawn after a later search, or the link is mistyped.
        </EmptyState>
      </>
    ) : (
      <LoadError what="This candidate" error={error.message} onRetry={() => setAttempt((n) => n + 1)} />
    );
  }

  if (!r) {
    return (
      <div aria-busy="true" style={{ display: "grid", gap: 16 }}>
        <div className={s.back}>{back}</div>
        <div className={l.skeleton} style={{ height: 180 }} role="status">
          <span className="sr-only">Loading the candidate</span>
        </div>
        <div className={l.skeleton} style={{ height: 300 }} />
      </div>
    );
  }

  const c = r.candidate;
  return (
    <>
      <div className={s.back}>{back}</div>
      <div className={s.reportGrid}>
        <div className={s.reportMain}>
          <Header c={c} demo={r.demo} onMap={hosts ? hosts.has(c.tic) : null} />

          <section className={s.section} aria-labelledby="dip-h">
            <div className={s.sectionHead}>
              <h2 id="dip-h" className={l.h2}>
                The dip
              </h2>
            </div>
            <p className={s.sectionLede}>
              A planet makes the same flat-bottomed dip every orbit. Stacking all dips on the period (left) shows its shape; the full record (right) shows each one
              lands where the period predicts.
            </p>
            <div className={s.charts}>
              <FoldedCurve c={c} />
              <UnfoldedCurve c={c} />
            </div>
            {r.demo && <p className={s.borrowed}>Demo: these light curves are simulated from the candidate&apos;s numbers.</p>}
          </section>

          <Checks c={c} />

          <section className={s.section} aria-labelledby="pixels-h">
            <div className={s.sectionHead}>
              <h2 id="pixels-h" className={l.h2}>
                Pixel check
              </h2>
            </div>
            <p className={s.sectionLede}>
              TESS pixels are big, so light from several stars can mix. Comparing the pixels between and during dips shows which star actually dimmed.
            </p>
            {r.pixels ? (
              <PixelCheck vet={r.pixels} demo={r.demo} />
            ) : (
              <EmptyState title="Pixel check not done yet">It runs after the checks; this report updates when it finishes.</EmptyState>
            )}
          </section>

          <KnownLists c={c} />
          <Score c={c} />
        </div>
        <aside className={s.aside} aria-label="Vote">
          <VoteBox id={c.id} initial={r.votes} demo={r.demo} />
        </aside>
      </div>
      <Footer c={c} />
    </>
  );
}
