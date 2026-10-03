import type { PixelMarker, PixelVet } from "@/lib/api";
import { verdictLabel } from "./finder";
import s from "./finder.module.css";

type Img = PixelVet["images"];

/** Ink on paper for the ordinary image (square-root stretch, so faint neighbours show). */
const greyFill = (t: number) => `color-mix(in oklab, var(--ink) ${Math.round(Math.min(1, Math.max(0, t)) * 100)}%, var(--paper))`;
/** Pen where light was lost during the dip, catalogue blue where it rose. */
const diffFill = (t: number) =>
  t >= 0
    ? `color-mix(in oklab, var(--pen) ${Math.round(Math.min(1, t) * 100)}%, var(--paper))`
    : `color-mix(in oklab, var(--known) ${Math.round(Math.min(1, -t) * 100)}%, var(--paper))`;

function Diamond({ m, n, suspect }: { m: PixelMarker; n: number; suspect: boolean }) {
  const r = 0.2;
  const y = n - 1 - m.y;
  return (
    <path className={suspect ? s.markSuspect : s.markNeighbour} d={`M${m.x} ${y - r}L${m.x + r} ${y}L${m.x} ${y + r}L${m.x - r} ${y}Z`}>
      <title>{`Gaia DR3 ${m.gaia_id}${m.gmag != null ? `, G ${m.gmag.toFixed(1)}` : ""}`}</title>
    </path>
  );
}

/** One image as a pixel grid. Row 0 is at the bottom, as astronomers draw it. */
function Heatmap({ img, which, suspects }: { img: Img; which: "out" | "diff"; suspects: Set<string> }) {
  const data = which === "out" ? img.out_of_transit : img.difference;
  const n = data.length;
  const cols = data[0]?.length ?? 0;
  const flat = data.flat().filter(Number.isFinite);
  const hiOut = Math.sqrt(Math.max(...flat, 1));
  const hiDiff = Math.max(...flat.map(Math.abs), 1e-9);
  const fill = which === "out" ? (v: number) => greyFill(Math.sqrt(Math.max(v, 0)) / hiOut) : (v: number) => diffFill(v / hiDiff);
  const target = img.markers.find((m) => m.kind === "target");
  const c = img.centroid;
  const arm = 0.34;
  return (
    <figure className={s.heat}>
      <svg
        className={s.heatSvg}
        viewBox={`-0.5 -0.5 ${cols} ${n}`}
        role="img"
        aria-label={
          which === "out"
            ? `The ${cols} by ${n} TESS pixels around the star between dips. The target is ringed; Gaia neighbours bright enough to fake the dip are diamonds.`
            : `Where light went missing during the dips.${c ? " The cross marks its centre." : ""}`
        }
      >
        {data.map((row, j) => row.map((v, i) => <rect key={`${i}-${j}`} x={i - 0.5} y={n - 1 - j - 0.5} width={1.02} height={1.02} style={{ fill: fill(v) }} />))}
        {img.markers
          .filter((m) => m.kind !== "target" && (m.kind === "suspect" || (!!m.gaia_id && suspects.has(m.gaia_id)) || (m.needed_depth != null && m.needed_depth < 1)))
          .map((m) => (
            <Diamond key={m.gaia_id ?? `${m.x},${m.y}`} m={m} n={n} suspect={m.kind === "suspect" || (!!m.gaia_id && suspects.has(m.gaia_id))} />
          ))}
        {target && <circle className={s.markTarget} cx={target.x} cy={n - 1 - target.y} r={0.42} />}
        {which === "diff" && c && <path className={s.markCentroid} d={`M${c.x - arm} ${n - 1 - c.y}h${2 * arm}M${c.x} ${n - 1 - c.y - arm}v${2 * arm}`} />}
      </svg>
      <figcaption className={s.cap}>
        <span className="label">{which === "out" ? "Between dips" : "Light lost in the dips"}</span>
        <span>
          {which === "out"
            ? `The star and its neighbours${img.sector ? `, sector ${img.sector}` : ""}.${img.pixel_scale_arcsec ? ` Each pixel is ${Math.round(img.pixel_scale_arcsec)}″ across.` : ""}`
            : "Red where light went missing, blue where it rose. The cross is the centre of the missing light."}
        </span>
      </figcaption>
    </figure>
  );
}

const sentence = (t: string) => t.charAt(0).toUpperCase() + t.slice(1) + (/[.!?]$/.test(t) ? "" : ".");

export function PixelCheck({ vet }: { vet: PixelVet }) {
  const suspects = new Set(vet.suspect_neighbours.map((x) => x.gaia_id));
  return (
    <div className={s.pixels}>
      <p className={s.verdictLine}>
        <span className={s.verdict} data-verdict={vet.verdict}>
          {verdictLabel(vet.verdict)}
        </span>
        <span>{sentence(vet.reason)}</span>
      </p>
      <div className={s.heatPair}>
        <Heatmap img={vet.images} which="out" suspects={suspects} />
        <Heatmap img={vet.images} which="diff" suspects={suspects} />
      </div>
      <dl className={s.facts}>
        <div>
          <dt className="label">Centre offset</dt>
          <dd className="num">
            {vet.centroid_offset_arcsec != null ? `${vet.centroid_offset_arcsec.toFixed(1)}″` : "none measured"}
            {vet.offset_sigma != null ? `, ${vet.offset_sigma.toFixed(0)}σ` : ""}
          </dd>
        </div>
        <div>
          <dt className="label">On the target</dt>
          <dd className="num">{vet.on_target_probability != null ? `${Math.round(vet.on_target_probability * 100)}%` : "not estimated"}</dd>
        </div>
        <div>
          <dt className="label">Key</dt>
          <dd className={s.key}>
            <span>
              <svg viewBox="-0.6 -0.6 1.2 1.2" aria-hidden>
                <circle className={s.markTarget} r={0.4} />
              </svg>
              target
            </span>
            <span>
              <svg viewBox="-0.6 -0.6 1.2 1.2" aria-hidden>
                <path className={s.markNeighbour} d="M0 -0.4L0.4 0L0 0.4L-0.4 0Z" />
              </svg>
              neighbour bright enough to fake it
            </span>
            <span>
              <svg viewBox="-0.6 -0.6 1.2 1.2" aria-hidden>
                <path className={s.markSuspect} d="M0 -0.4L0.4 0L0 0.4L-0.4 0Z" />
              </svg>
              the likeliest source
            </span>
          </dd>
        </div>
      </dl>
    </div>
  );
}
