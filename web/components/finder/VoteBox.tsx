"use client";

import { useEffect, useReducer, useRef } from "react";
import { CheckCircle, Question, XCircle } from "@phosphor-icons/react";
import { submitVote, type VoteChoice, type Votes } from "@/lib/api";
import { initVotes, REASONS, voteReducer } from "./finder";
import s from "./finder.module.css";

const OPTIONS: { value: VoteChoice; label: string; Icon: typeof CheckCircle }[] = [
  { value: "planet", label: "Looks like a planet", Icon: CheckCircle },
  { value: "fake", label: "Looks like a fake", Icon: XCircle },
  { value: "unsure", label: "Not sure", Icon: Question },
];

export function VoteBox({ id, initial, demo }: { id: string; initial: Votes; demo: boolean }) {
  const [state, dispatch] = useReducer(voteReducer, initial, initVotes);
  // Save whatever the viewer last chose; an older reply that lands late is ignored.
  const seq = useRef(0);
  const pending = state.status === "saving";
  const { mine, reasons } = state;
  useEffect(() => {
    if (!pending) return;
    const n = ++seq.current;
    submitVote(id, mine, reasons)
      .then((v) => n === seq.current && dispatch({ type: "saved", votes: v }))
      .catch((e: unknown) => n === seq.current && dispatch({ type: "failed", message: e instanceof Error ? e.message : String(e) }));
  }, [id, pending, mine, reasons]);

  const total = state.counts.planet + state.counts.fake + state.counts.unsure;
  const status =
    state.status === "saving"
      ? "Saving"
      : state.status === "error"
        ? `Your vote didn't save (${state.error}). Try again.`
        : state.mine
          ? `Your vote is in${demo ? ", kept in this browser (demo)" : ""}. Choose it again to take it back.`
          : total === 0
            ? "No votes yet. Be the first."
            : "";

  return (
    <section className={s.vote} aria-labelledby="vote-h">
      <div style={{ display: "grid", gap: 4 }}>
        <h2 id="vote-h" className={s.voteQ}>
          What do you think?
        </h2>
        <p className={s.heatCaption}>
          <span className={s.num}>{total}</span> {total === 1 ? "person has" : "people have"} voted. Votes help decide which candidates are worth a telescope&apos;s
          time.
        </p>
      </div>
      <div className={s.voteOptions} role="group" aria-label="Your vote">
        {OPTIONS.map(({ value, label, Icon }) => (
          <button key={value} type="button" className={s.voteOption} aria-pressed={state.mine === value} onClick={() => dispatch({ type: "choose", choice: value })}>
            <Icon className={s.voteIcon} size={18} weight={state.mine === value ? "fill" : "regular"} aria-hidden />
            <span>{label}</span>
            <span className={s.voteCount} aria-label={`${state.counts[value]} votes`}>
              {state.counts[value]}
            </span>
          </button>
        ))}
      </div>
      <fieldset style={{ border: 0, margin: 0, padding: 0, display: "grid", gap: 8 }} disabled={!state.mine}>
        <legend className="label" style={{ padding: 0, marginBottom: 8 }}>
          Why? Optional
        </legend>
        <div className={s.chips}>
          {REASONS.map((r) => (
            <button key={r.id} type="button" className={s.chip} aria-pressed={state.reasons.includes(r.id)} onClick={() => dispatch({ type: "toggleReason", id: r.id })}>
              {r.label}
            </button>
          ))}
        </div>
        {!state.mine && <p className={s.heatCaption}>Vote first, then add a reason if one fits.</p>}
      </fieldset>
      <p className={s.voteStatus} data-status={state.status} role="status" aria-live="polite">
        {status}
      </p>
    </section>
  );
}
