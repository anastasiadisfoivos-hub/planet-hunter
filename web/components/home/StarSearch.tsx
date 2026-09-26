"use client";

// Find a star by name, planet name or TIC number. A planet host opens its lab page
// (/lab/star/<tic>); anything else goes to the sky map as a search (/map?q=...).

import { useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import type { HostsFile } from "@/lib/data";
import s from "./home.module.css";

type Entry = { name: string; tic: number; key: string; also: string[]; planets: number };

const norm = (q: string) => q.toLowerCase().replace(/[^a-z0-9]/g, "");
const MAX = 6;

let hosts: Promise<Entry[]> | null = null;
function loadHosts(): Promise<Entry[]> {
  hosts ??= fetch("/data/hosts.json")
    .then((r) => (r.ok ? (r.json() as Promise<HostsFile>) : Promise.reject(r.status)))
    .then((h) => h.name.map((name, i) => ({ name, tic: h.tic[i], key: norm(name), also: (h.planets[i] ?? []).map(norm), planets: h.npl[i] })))
    .catch((e) => {
      hosts = null;
      throw e;
    });
  return hosts;
}

/** The host a query names exactly: a TIC number, a star name or one of its planets. */
function exact(list: Entry[], q: string): Entry | null {
  const n = norm(q);
  if (!n) return null;
  const tic = /^(tic)?(\d+)$/.exec(n);
  if (tic) return list.find((e) => e.tic === Number(tic[2])) ?? null;
  return list.find((e) => e.key === n || e.also.includes(n)) ?? null;
}

function suggest(list: Entry[], q: string): Entry[] {
  const n = norm(q);
  if (n.length < 2) return [];
  const starts = list.filter((e) => e.key.startsWith(n));
  const within = list.filter((e) => !e.key.startsWith(n) && e.key.includes(n));
  return [...starts.sort((a, b) => a.key.length - b.key.length), ...within].slice(0, MAX);
}

export function StarSearch() {
  const router = useRouter();
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [list, setList] = useState<Entry[] | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const options = list ? suggest(list, q) : [];
  const shown = open && options.length > 0;

  const warm = () => {
    if (!list) loadHosts().then(setList, () => undefined);
  };

  const go = async (pick: Entry | null) => {
    const query = q.trim();
    if (!pick && !query) {
      input.current?.focus();
      return;
    }
    let target = pick;
    if (!target) {
      try {
        target = exact(list ?? (await loadHosts()), query);
      } catch {
        target = null;
      }
    }
    setOpen(false);
    router.push(target ? `/lab/star/${target.tic}` : `/map?q=${encodeURIComponent(query)}`);
  };

  return (
    <form
      className={s.search}
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        go(shown && active >= 0 ? options[active] : null);
      }}
    >
      <label htmlFor={`${id}-q`} className={s.searchLabel}>
        Find a star
      </label>
      <div className={s.searchRow}>
        <div className={s.searchField}>
          <MagnifyingGlass size={16} aria-hidden className={s.searchIcon} />
          <input
            ref={input}
            id={`${id}-q`}
            className={s.searchInput}
            type="text"
            inputMode="search"
            autoComplete="off"
            spellCheck={false}
            placeholder="WASP-18, TOI-700 or a TIC number"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={shown}
            aria-controls={`${id}-list`}
            aria-describedby={`${id}-help`}
            aria-activedescendant={shown && active >= 0 ? `${id}-o${active}` : undefined}
            value={q}
            onFocus={warm}
            onBlur={() => setOpen(false)}
            onChange={(e) => {
              warm();
              setQ(e.target.value);
              setOpen(true);
              setActive(-1);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" && options.length) {
                e.preventDefault();
                setOpen(true);
                setActive((a) => (a + 1) % options.length);
              } else if (e.key === "ArrowUp" && options.length) {
                e.preventDefault();
                setOpen(true);
                setActive((a) => (a <= 0 ? options.length - 1 : a - 1));
              } else if (e.key === "Escape") {
                setOpen(false);
              }
            }}
          />
          <ul id={`${id}-list`} role="listbox" aria-label="Planet hosts" className={s.options} hidden={!shown}>
            {options.map((o, i) => (
              <li
                key={o.tic}
                id={`${id}-o${i}`}
                role="option"
                aria-selected={i === active}
                className={s.option}
                // mousedown, not click: it fires before the input's blur closes the list.
                onMouseDown={(e) => {
                  e.preventDefault();
                  go(o);
                }}
              >
                <span>{o.name}</span>
                <span className={s.optionMeta}>
                  TIC {o.tic} · {o.planets} {o.planets === 1 ? "planet" : "planets"}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <Button type="submit" variant="primary" className={s.searchButton}>
          Search
        </Button>
      </div>
      <p id={`${id}-help`} className={s.searchHelp}>
        Stars with known planets open in the Lab. Anything else is looked up on the sky map.
      </p>
    </form>
  );
}
