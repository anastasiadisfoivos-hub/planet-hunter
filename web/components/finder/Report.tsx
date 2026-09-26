"use client";

// /finder/[id]: the folded dip is the lead picture; the survey picture of the star's field is the small one beside it.
// Title, one line and four facts; the vote; the whole light curve and the pixels; every explanation in a drawer
// (DESIGN.md, Drawers). Vote counts show only after you vote (VoteBox).

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowSquareOut, CheckCircle, MinusCircle, XCircle } from "@phosphor-icons/react";
import { Drawer } from "@/components/picture/Drawer";
import { Picture } from "@/components/picture/Picture";
import { ButtonLink, DemoTag, EmptyState } from "@/components/ui";
import { LoadError } from "@/components/lab/chart";
import { ApiError, getCandidate, getMapHostTics, type Candidate, type CandidateReport } from "@/lib/api";
import { formatUtc } from "@/lib/format";
import { honesty, sourceName, starPic } from "@/lib/pictures";
import { BTJD_TO_BJD, checkLabel, fmtCheckValue, fmtDepth, KNOWN_LISTS, listMatch, partLabel, rEarth, SCORE_PARTS, sizeClass, verdictLabel } from "./finder";
import { FoldedCurve, UnfoldedCurve } from "./LightCurves";
import { PixelCheck } from "./Pixels";
import { VoteBox } from "./VoteBox";
import r from "./report.module.css";
import s from "./finder.module.css";

const fmtDay = (iso: string) => formatUtc(iso).split(",")[0];
const PART_COLORS = ["var(--ink)", "var(--ink-secondary)", "var(--ink-muted)", "var(--ink-disabled)"];

function Checks({ c }: { c: Candidate }) {
  return (
    <ul className={s.checkList}>
      {c.checks.map((k) => {
        const st = k.passed === true ? "pass" : k.passed === false ? "fail" : "skip";
        const Icon = st === "pass" ? CheckCircle : st === "fail" ? XCircle : MinusCircle;
        return (
          <li key={k.name} className={s.checkRow} data-state={st}>
            <Icon className={s.checkIcon} data-state={st} size={18} aria-label={st === "pass" ? "Passed" : st === "fail" ? "Failed" : "Couldn't run"} />
            <span className={s.checkName}>{checkLabel(k.name)}</span>
            <span className={s.checkValue}>{fmtCheckValue(k.name, k.value)}</span>
            <p className={s.checkReason}>{k.reason}</p>
          </li>
        );
      })}
    </ul>
  );
}

function Priority({ c }: { c: Candidate }) {
  const parts = Object.entries(c.score_parts);
  return (
    <>
      <p>{c.score.toFixed(2)} of 1, a machine ranking. It orders the list; it is not the chance this is a planet.</p>
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
    </>
  );
}

function Numbers({ c }: { c: Candidate }) {
  const rows: [string, string][] = [
    ["Period", `${c.period_d.toFixed(5)} days`],
    ["Size", `${rEarth(c.radius_rjup).toFixed(1)} × Earth, likely ${rEarth(c.radius_low).toFixed(1)} to ${rEarth(c.radius_high).toFixed(1)} (${sizeClass(c.radius_rjup)})`],
    ["Dip depth", `${fmtDepth(c.depth_ppm)}, ${Math.round(c.depth_ppm)} ppm of the starlight`],
    ["Dip length", `${c.duration_h.toFixed(1)} hours, ${c.n_transits} dips seen`],
    ["Signal", `SNR ${c.snr.toFixed(1)}, SDE ${c.sde.toFixed(1)}`],
    ["First dip", `${c.t0_btjd.toFixed(4)} BTJD, or BJD ${(c.t0_btjd + BTJD_TO_BJD).toFixed(4)}`],
  ];
  return (
    <dl className={r.numbers}>
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt className="label">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Report({ id }: { id: string }) {
  const [rep, setRep] = useState<CandidateReport | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [hosts, setHosts] = useState<Set<number> | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    getCandidate(id, ctl.signal)
      .then((v) => {
        setRep(v);
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
    <Link href="/finder" className={r.crumb}>
      <ArrowLeft size={14} aria-hidden />
      Candidates
    </Link>
  );

  if (error) {
    return error.status === 404 ? (
      <>
        {back}
        <EmptyState title="No candidate with that name" action={<ButtonLink href="/finder">See all candidates</ButtonLink>}>
          It may have been withdrawn after a later search, or the link is mistyped.
        </EmptyState>
      </>
    ) : (
      <LoadError what="This candidate" error={error.message} onRetry={() => setAttempt((n) => n + 1)} />
    );
  }

  if (!rep) {
    return (
      <div aria-busy="true">
        {back}
        <div className={r.lead}>
          <div className={r.skeleton} style={{ aspectRatio: "16 / 9" }} role="status">
            <span className="sr-only">Loading the candidate</span>
          </div>
          <div className={r.skeleton} style={{ aspectRatio: "1" }} />
        </div>
      </div>
    );
  }

  const c = rep.candidate;
  const field = starPic(c.tic);
  const onMap = hosts?.has(c.tic) ?? false;
  const passed = c.checks.filter((k) => k.passed === true).length;
  const verdict = rep.pixels?.verdict ?? null;

  return (
    <>
      {back}
      <div className={r.lead}>
        <figure className={r.fold}>
          <FoldedCurve c={c} height={420} bare />
          <figcaption className="cap">
            {c.n_transits} dips stacked · TESS sector{c.sectors.length > 1 ? "s" : ""} {c.sectors.join(", ")}
            {rep.demo ? " · demo" : ""}
          </figcaption>
        </figure>
        {field ? (
          <Picture
            pic={field}
            alt={`Survey picture of the sky around TIC ${c.tic}; the crosshair marks the star`}
            sizes="(max-width: 1023px) 100vw, 400px"
            aspect="1 / 1"
            caption={`${sourceName(field)} · archive`}
            note={honesty(null, field)}
            className={r.field}
          />
        ) : (
          <div />
        )}
      </div>

      <div className={r.split}>
        <div>
          <span className="label">Planet candidate</span>
          <div className={r.titleRow}>
            <h1 className={r.h1}>TIC {c.tic}</h1>
            {rep.demo && <DemoTag />}
          </div>
          <p className={r.line}>
            {c.name ? `Around ${c.name}. ` : ""}A dip every {c.period_d.toFixed(2)} days. A candidate, not a planet.
          </p>
          <dl className={r.facts}>
            <div>
              <dt className="label">Period</dt>
              <dd>
                <span className="mono">{c.period_d.toFixed(2)}</span>
                <span className={r.unit}>days</span>
              </dd>
            </div>
            <div>
              <dt className="label">Size</dt>
              <dd>
                <span className="mono">{rEarth(c.radius_rjup).toFixed(1)}</span>
                <span className={r.unit}>× Earth</span>
              </dd>
            </div>
            <div>
              <dt className="label">Checks</dt>
              <dd>
                <span className="mono">{passed}</span>
                <span className={r.unit}>of {c.checks.length}</span>
              </dd>
            </div>
            <div>
              <dt className="label">Priority</dt>
              <dd>
                <span className="mono">{c.score.toFixed(2)}</span>
              </dd>
            </div>
          </dl>
          {onMap ? (
            <div className={r.actions}>
              <ButtonLink href={`/lab/star/${c.tic}`}>Open star lab</ButtonLink>
              <ButtonLink href={`/sky?host=${c.tic}`} variant="quiet">
                See it on the sky
              </ButtonLink>
            </div>
          ) : (
            <p className={r.note}>Found {fmtDay(c.created_at)}. This star has no lab page or sky position yet.</p>
          )}
        </div>
        <aside className={r.vote} aria-label="Vote">
          <VoteBox id={c.id} initial={rep.votes} demo={rep.demo} />
        </aside>
      </div>

      <section className={r.block} aria-label="The whole light curve">
        <UnfoldedCurve c={c} />
      </section>

      <section className={r.block} aria-label="Pixel check">
        {rep.pixels ? <PixelCheck vet={rep.pixels} demo={rep.demo} /> : <EmptyState title="Pixel check not done yet">It runs after the checks; this report updates when it finishes.</EmptyState>}
      </section>

      <section className={r.block} aria-label="How we know">
        <Drawer title="Checks" state={`${passed} of ${c.checks.length} passed`}>
          <p>Tests that catch the usual false alarms: noise, two stars eclipsing each other, and light from a neighbour. Every test is listed, passed or not.</p>
          <Checks c={c} />
        </Drawer>
        <Drawer title="Pixel check" state={verdictLabel(verdict)}>
          <p>TESS pixels are 21″ across, so light from several stars can mix. Comparing the pixels between and during dips shows which star actually dimmed.</p>
          {rep.demo && <p>Demo: these pixel images are borrowed from a real pixel check of another star.</p>}
        </Drawer>
        <Drawer title="Known lists" state={KNOWN_LISTS.some((k) => listMatch(c.known_lists[k.key]).matched) ? "On a list" : "On none"}>
          <p>The signal was compared by star and period with these lists. &quot;Not on the list&quot; means no match in the copy we checked.</p>
          <ul className={r.lists}>
            {KNOWN_LISTS.map((k) => {
              const m = listMatch(c.known_lists[k.key]);
              return (
                <li key={k.key}>
                  <span>{k.label}</span>
                  <span className="cap">{m.matched ? `On the list${m.id ? `: ${m.id}` : ""}` : "Not on the list"}</span>
                  <a href={k.url} target="_blank" rel="noreferrer">
                    {k.source}
                  </a>
                </li>
              );
            })}
          </ul>
        </Drawer>
        <Drawer title="Priority" state={c.score.toFixed(2)}>
          <Priority c={c} />
        </Drawer>
        <Drawer title="All the numbers" state="6 values">
          <Numbers c={c} />
        </Drawer>
        <Drawer title="What a candidate is" state="About">
          <p>A repeating dip in a star&apos;s light that passed our checks and is on none of the lists we compared. Many turn out to be eclipsing stars, a blended neighbour or an instrument effect. None of them is a planet yet.</p>
          <p>Confirmation needs follow-up by professionals: sharper images, more dips from the ground, and usually the star&apos;s wobble measured with a spectrograph. That takes months to years.</p>
          <p>
            Strong candidates can be posted to{" "}
            <a href={`https://exofop.ipac.caltech.edu/tess/target.php?id=${c.tic}`} target="_blank" rel="noreferrer">
              ExoFOP <ArrowSquareOut size={12} aria-hidden style={{ verticalAlign: "-1px" }} />
            </a>{" "}
            as a Community TOI. Posting is a review step, not a claim.
          </p>
        </Drawer>
      </section>
    </>
  );
}
