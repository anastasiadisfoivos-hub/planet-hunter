"use client";

// The home page's background: the real bright stars (Yale BSC, via sky-objects.json) in their true
// colours (lib/starColor.ts), on pure black, around Orion. It turns very slowly the way the sky does,
// faster than real time so it reads as alive. Still under reduced motion, on phones, off screen and in
// hidden tabs. No nebula, no twinkle: the same rules as the map's sky.

import { useEffect, useRef } from "react";
import type { SkyObjectsFile } from "@/lib/data";
import { bvToTeff, starColor } from "@/lib/starColor";
import s from "./home.module.css";

const DEG = Math.PI / 180;
/** Degrees of right ascension per second. The real sky turns at 0.0042 deg/s; this is about 30 times that. */
const DRIFT = 0.12;
const START_RA = 84; // Orion's belt
const DEC0 = 4 * DEG;

type Star = { ra: number; dec: number; r: number; a: number; color: string; halo: boolean };

function toStars(sky: SkyObjectsFile["stars"]): Star[] {
  const out: Star[] = [];
  for (let i = 0; i < sky.ra.length; i++) {
    const mag = sky.mag[i];
    const [r, g, b] = starColor(Number.isFinite(sky.bv[i]) ? bvToTeff(sky.bv[i]) : 0);
    out.push({
      ra: sky.ra[i] * DEG,
      dec: sky.dec[i] * DEG,
      r: Math.max(0.55, 2.9 - 0.42 * mag),
      a: Math.min(1, Math.max(0.2, 1.1 - (mag + 1) / 9)),
      color: `${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)}`,
      halo: mag < 2.4,
    });
  }
  return out;
}

export function HeroSky() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = canvas.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const ctl = new AbortController();
    let stars: Star[] = [];
    let raf = 0;
    let visible = true;
    let ra0 = START_RA * DEG;
    let last = 0;
    const still = window.matchMedia("(prefers-reduced-motion: reduce), (max-width: 700px)");

    const draw = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const phone = w < 700;
      // Stereographic projection, about 110 degrees across, east to the left as seen from Earth.
      const scale = w / (4 * Math.tan((phone ? 80 : 110) * DEG * 0.25));
      const cx = phone ? w * 0.5 : w * 0.62;
      const cy = h * 0.5;
      const sd0 = Math.sin(DEC0);
      const cd0 = Math.cos(DEC0);
      for (const st of stars) {
        const dra = st.ra - ra0;
        const cd = Math.cos(st.dec);
        const sdd = Math.sin(st.dec);
        const cosc = sd0 * sdd + cd0 * cd * Math.cos(dra);
        if (cosc < -0.2) continue;
        const k = 2 / (1 + cosc);
        const x = cx - k * cd * Math.sin(dra) * scale;
        const y = cy - k * (cd0 * sdd - sd0 * cd * Math.cos(dra)) * scale;
        if (x < -20 || x > w + 20 || y < -20 || y > h + 20) continue;
        // Quieter behind the words: the left of the hero on desktop, everywhere on a phone.
        const quiet = phone ? 0.38 : 0.3 + 0.7 * Math.min(1, Math.max(0, (x / w - 0.4) / 0.22));
        const a = st.a * quiet;
        if (st.halo) {
          const g = ctx.createRadialGradient(x, y, 0, x, y, st.r * 5);
          g.addColorStop(0, `rgba(${st.color},${a * 0.45})`);
          g.addColorStop(1, `rgba(${st.color},0)`);
          ctx.fillStyle = g;
          ctx.fillRect(x - st.r * 5, y - st.r * 5, st.r * 10, st.r * 10);
        }
        ctx.fillStyle = `rgba(${st.color},${a})`;
        ctx.beginPath();
        ctx.arc(x, y, st.r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const tick = (t: number) => {
      raf = 0;
      if (last) ra0 += DRIFT * DEG * Math.min(0.1, (t - last) / 1000);
      last = t;
      draw();
      schedule();
    };
    const schedule = () => {
      if (!raf && visible && !document.hidden && !still.matches && stars.length) raf = requestAnimationFrame(tick);
    };
    const wake = () => {
      last = 0;
      schedule();
    };

    fetch("/data/sky-objects.json", { signal: ctl.signal })
      .then((r) => (r.ok ? (r.json() as Promise<SkyObjectsFile>) : Promise.reject(r.status)))
      .then((sky) => {
        stars = toStars(sky.stars);
        draw();
        schedule();
      })
      .catch(() => {
        /* the hero is plain black without it */
      });

    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      wake();
    });
    io.observe(cv);
    const ro = new ResizeObserver(() => draw());
    ro.observe(cv);
    document.addEventListener("visibilitychange", wake, { signal: ctl.signal });
    still.addEventListener("change", wake, { signal: ctl.signal });

    return () => {
      ctl.abort();
      io.disconnect();
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas ref={canvas} className={s.sky} aria-hidden />;
}
