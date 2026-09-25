import type { PixelMarker, PixelVet } from "@/lib/api";
import { VerdictBadge } from "./Verdict";
import s from "./finder.module.css";

type Img = PixelVet["images"];

/** Grey ramp for the ordinary image (square-root stretch, so faint neighbours show). */
const greyFill = (t: number) => `color-mix(in oklab, var(--ink) ${Math.round(Math.min(1, Math.max(0, t)) * 100)}%, var(--bg-deep))`;
/** Warm where light was lost during the dip, cool where it rose; both fade to the chart background at zero. */
const diffFill = (t: number) =>
  t >= 0
    ? `color-mix(in oklab, var(--cat-sun) ${Math.round(Math.min(1, t) * 100)}%, var(--bg-deep))`
    : `color-mix(in oklab, var(--cat-earth) ${Math.round(Math.min(1, -t) * 100)}%, var(--bg-deep))`;

function Diamond({ m, cls, n }: { m: PixelMarker; cls: string; n: number }) {
  const r = 0.26;
  const y = n - 1 - m.y;
  const d = `M${m.x} ${y - r}L${m.x + r} ${y}L${m.x} ${y + r}L${m.x - r} ${y}Z`;
  return (
    <>
      <path className={s.markHalo} d={d} />
      <path className={cls} d={d}>
        <title>
          Gaia DR3 {m.gaia_id}
          {m.gmag != null ? `, G=${m.gmag.toFixed(1)}` : ""}
          {m.needed_depth != null ? `, would need a ${m.needed_depth >= 1 ? "more than total" : `${(m.needed_depth * 100).toFixed(1)}%`} eclipse` : ""}
        </title>
      </path>
    </>
  );
}

/** One image as a pixel grid. Row 0 is at the bottom, as astronomers draw it. */
function Heatmap({ img, which, suspects }: { img: Img; which: "out" | "diff"; suspects: Set<string> }) {
  const data = which === "out" ? img.out_of_transit : img.difference;
  const rows = data.length;
  const cols = data[0]?.length ?? 0;
  const n = rows;
  const flat = data.flat().filter(Number.isFinite);
  let fill: (v: number) => string;
  let rampCss: string;
  let rampLabels: [string, string];
  if (which === "out") {
    const hi = Math.sqrt(Math.max(...flat, 1));
    fill = (v) => greyFill(Math.sqrt(Math.max(v, 0)) / hi);
    rampCss = "linear-gradient(90deg, var(--bg-deep), var(--ink))";
    rampLabels = ["Faint", "Bright"];
  } else {
    const hi = Math.max(...flat.map(Math.abs), 1e-9);
    fill = (v) => diffFill(v / hi);
    rampCss = "linear-gradient(90deg, var(--cat-earth), var(--bg-deep), var(--cat-sun))";
    rampLabels = ["Got brighter", "Lost light"];
  }
  const target = img.markers.find((m) => m.kind === "target");
  const neighbours = img.markers.filter((m) => m.kind !== "target");
  const c = img.centroid;
  const arm = 0.32;
  const compass = img.compass;
  const label = which === "out" ? "Out of transit" : "Difference";
  return (
    <figure className={s.heat} style={{ margin: 0 }}>
      <span className="label">{label}</span>
      <svg
        className={s.heatSvg}
        viewBox={`-0.5 -0.5 ${cols} ${rows}`}
        role="img"
        aria-label={
          which === "out"
            ? `The ${cols} by ${rows} TESS pixels around the star between dips. The target is ringed; nearby Gaia stars are diamonds.`
            : `Where light went missing during the dips.${c ? " The cross marks the centre of the missing light." : " No clear spot: the dip is too faint to see in single pixels."}`
        }
      >
        {data.map((row, j) =>
          row.map((v, i) => (
            <rect key={`${i}-${j}`} x={i - 0.5} y={n - 1 - j - 0.5} width={1.02} height={1.02} style={{ fill: fill(v) }}>
              <title>{`pixel (${i}, ${j}): ${v.toFixed(which === "out" ? 1 : 3)} e⁻/s`}</title>
            </rect>
          )),
        )}
        {neighbours.map((m) => (
          <Diamond key={m.gaia_id ?? `${m.x},${m.y}`} m={m} n={n} cls={m.kind === "suspect" || (m.gaia_id && suspects.has(m.gaia_id)) ? s.markSuspect : s.markNeighbour} />
        ))}
        {target && (
          <>
            <circle className={s.markHalo} cx={target.x} cy={n - 1 - target.y} r={0.42} />
            <circle className={s.markTarget} cx={target.x} cy={n - 1 - target.y} r={0.42}>
              <title>{target.label ?? "Target"}</title>
            </circle>
          </>
        )}
        {which === "diff" && c && (
          <g>
            <path className={s.markHalo} d={`M${c.x - arm} ${n - 1 - c.y}h${2 * arm}M${c.x} ${n - 1 - c.y - arm}v${2 * arm}`} />
            <path className={s.markCentroid} d={`M${c.x - arm} ${n - 1 - c.y}h${2 * arm}M${c.x} ${n - 1 - c.y - arm}v${2 * arm}`}>
              <title>Centre of the missing light</title>
            </path>
          </g>
        )}
        {which === "out" && compass && (
          <g transform={`translate(${cols - 1.6} ${0.9})`} aria-hidden>
            {(["north", "east"] as const).map((k) => {
              const [dx, dy] = compass[k];
              return (
                <g key={k}>
                  <line className={s.compass} x1={0} y1={0} x2={dx * 0.7} y2={-dy * 0.7} />
                  <text className={s.compassText} x={dx * 1.0} y={-dy * 1.0 + 0.14} textAnchor="middle">
                    {k === "north" ? "N" : "E"}
                  </text>
                </g>
              );
            })}
          </g>
        )}
      </svg>
      <div className={s.ramp} style={{ background: rampCss }} aria-hidden />
      <div className={s.rampLabels} aria-hidden>
        <span>{rampLabels[0]}</span>
        <span>{rampLabels[1]}</span>
      </div>
      <figcaption className={s.heatCaption}>
        {which === "out"
          ? `The star and its neighbours between dips${img.sector ? `, sector ${img.sector}` : ""}.${img.pixel_scale_arcsec ? ` Each pixel is ${Math.round(img.pixel_scale_arcsec)}″ across.` : ""}`
          : "Between dips minus during dips: the bright spot shows where the light went missing."}
      </figcaption>
    </figure>
  );
}

const pct = (p: number) => `${Math.round(p * 100)}%`;
const capital = (t: string) => t.charAt(0).toUpperCase() + t.slice(1) + (/[.!?]$/.test(t) ? "" : ".");

export function PixelCheck({ vet, demo }: { vet: PixelVet; demo: boolean }) {
  const suspects = new Set(vet.suspect_neighbours.map((n) => n.gaia_id));
  return (
    <>
      <div className={s.pixelTop}>
        <div>
          <VerdictBadge verdict={vet.verdict} />
        </div>
        <p className={s.verdictReason}>{capital(vet.reason)}</p>
      </div>
      <div className={s.pixelGrid}>
        <Heatmap img={vet.images} which="out" suspects={suspects} />
        <Heatmap img={vet.images} which="diff" suspects={suspects} />
        <dl className={s.pixelStats}>
          <div>
            <dt className="label">On the target</dt>
            <dd>{vet.on_target_probability != null ? pct(vet.on_target_probability) : "can't tell"}</dd>
            <span className={s.heatCaption}>Chance the dip is on this star, from where the light went missing.</span>
          </div>
          <div>
            <dt className="label">Centre offset</dt>
            <dd>
              {vet.centroid_offset_arcsec != null ? `${vet.centroid_offset_arcsec.toFixed(1)}″` : "none measured"}
              {vet.offset_sigma != null && <span className={s.muted}>{`, ${vet.offset_sigma.toFixed(1)}σ`}</span>}
            </dd>
            <span className={s.heatCaption}>Distance from the star to the centre of the missing light, and how sure that shift is.</span>
          </div>
          <div>
            <dt className="label">Key</dt>
            <dd style={{ display: "grid", gap: 6, fontFamily: "var(--font-sans)", fontSize: "var(--text-12)", color: "var(--ink-secondary)" }}>
              <span>
                <svg className={s.keySym} viewBox="-0.6 -0.6 1.2 1.2" aria-hidden>
                  <circle className={s.markTarget} r={0.42} style={{ strokeWidth: 0.16 }} />
                </svg>{" "}
                Target star
              </span>
              <span>
                <svg className={s.keySym} viewBox="-0.6 -0.6 1.2 1.2" aria-hidden>
                  <path className={s.markNeighbour} d="M0 -0.4L0.4 0L0 0.4L-0.4 0Z" style={{ strokeWidth: 0.14 }} />
                </svg>{" "}
                Gaia neighbour
              </span>
              <span>
                <svg className={s.keySym} viewBox="-0.6 -0.6 1.2 1.2" aria-hidden>
                  <path className={s.markSuspect} d="M0 -0.4L0.4 0L0 0.4L-0.4 0Z" style={{ strokeWidth: 0.16 }} />
                </svg>{" "}
                Neighbour that could cause it
              </span>
              <span>
                <svg className={s.keySym} viewBox="-0.6 -0.6 1.2 1.2" aria-hidden>
                  <path className={s.markCentroid} d="M-0.4 0h0.8M0 -0.4v0.8" style={{ strokeWidth: 0.16 }} />
                </svg>{" "}
                Centre of missing light
              </span>
            </dd>
          </div>
        </dl>
      </div>
      {vet.suspect_neighbours.length > 0 && (
        <div className={s.tableScroll}>
        <table className={s.suspects}>
          <caption className="label" style={{ textAlign: "left", paddingBottom: 8 }}>
            Neighbours that could cause the dip
          </caption>
          <thead>
            <tr>
              <th className="label">Gaia DR3</th>
              <th className="label">Distance</th>
              <th className="label">Brightness (G)</th>
              <th className="label">Its eclipse would need to be</th>
            </tr>
          </thead>
          <tbody>
            {vet.suspect_neighbours.map((n) => (
              <tr key={n.gaia_id}>
                <td>{n.gaia_id}</td>
                <td>{n.sep_arcsec.toFixed(1)}″</td>
                <td>{n.gmag.toFixed(1)}</td>
                <td>{n.needed_depth >= 1 ? "deeper than total: impossible" : `${(n.needed_depth * 100).toFixed(1)}% deep`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
      {demo && vet.images.borrowed_from && <p className={s.borrowed}>Demo: these images are real, copied from the pixel check of {vet.images.borrowed_from}.</p>}
    </>
  );
}
