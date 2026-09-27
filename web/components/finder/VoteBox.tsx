"use client";

import { useEffect, useReducer, useRef } from "react";
import { submitVote, type VoteChoice, type Votes } from "@/lib/api";
import { initVotes, REASONS, visibleCounts, voteReducer } from "./finder";
import s from "./finder.module.css";

const OPTIONS: { value: VoteChoice; label: string }[] = [
  { value: "planet", label: "Looks like a planet" },
  { value: "fake", label: "Probably not" },
  { value: "unsure", label: "Not sure" },
];

/** The vote (DESIGN.md: Words). Counts appear only after the viewer votes, so the crowd can't anchor them. */
export function VoteBox({ id, initial, demo }: { id: string; initial: Votes; demo: boolean }) {
  const [state, dispatch] = useReducer(voteReducer, initial, initVotes);
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

  const { counts, total } = visibleCounts(state);
  const status =
    state.status === "saving"
      ? "Saving."
      : state.status === "error"
        ? `Your vote didn't save (${state.error}). Try again.`
        : state.mine
          ? `Your vote is in${demo ? ", kept in this browser" : ""}. Choose it again to take it back.`
          : "";

  return (
    <div className={s.vote}>
      <p className={s.voteQ}>Does it look like a planet to you?</p>
      <p className="quiet">
        {total === 0 ? "Nobody has voted yet." : `${total} ${total === 1 ? "person has" : "people have"} voted.`} {counts ? "" : "You see how after you vote."}
      </p>
      <div className={s.voteOptions} role="group" aria-label="Your vote">
        {OPTIONS.map(({ value, label }) => (
          <button key={value} type="button" className="btn" aria-pressed={state.mine === value} onClick={() => dispatch({ type: "choose", choice: value })}>
            {label}
            {counts && <span className={s.voteCount}>{counts[value]}</span>}
          </button>
        ))}
      </div>
      <fieldset className={s.reasons} disabled={!state.mine}>
        <legend className="label">Why? Optional</legend>
        <div className={s.chips}>
          {REASONS.map((r) => (
            <button key={r.id} type="button" className={s.chip} aria-pressed={state.reasons.includes(r.id)} onClick={() => dispatch({ type: "toggleReason", id: r.id })}>
              {r.label}
            </button>
          ))}
        </div>
        {!state.mine && <p className={`${s.cap} quiet`}>Vote first, then add a reason if one fits.</p>}
      </fieldset>
      <p className={`${s.cap} italic`} data-status={state.status} role="status" aria-live="polite">
        {status}
      </p>
    </div>
  );
}
