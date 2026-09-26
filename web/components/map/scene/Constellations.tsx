"use client";

// Faint constellation lines on the sky sphere and the major constellations' names beside them, so a position
// reads as "in Orion, near the Milky Way". Lines and names: d3-celestial (BSD-3-Clause), public/data/sky/.

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import type { LinesData, NamesData } from "@/lib/galactic";
import { radecToVec } from "@/lib/sky";
import { SKY_R } from "./constants";

const R = SKY_R * 0.97;
const ra360 = (lon: number) => ((lon % 360) + 360) % 360;

export function Constellations({ visible }: { visible: boolean }) {
  const [data, setData] = useState<{ lines: LinesData; names: NamesData } | null>(null);
  const invalidate = useThree((s) => s.invalidate);
  const gl = useThree((s) => s.gl);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetch("/data/sky/constellation-lines.json").then((r) => r.json() as Promise<LinesData>),
      fetch("/data/sky/constellation-names.json").then((r) => r.json() as Promise<NamesData>),
    ]).then(
      ([lines, names]) => {
        if (!live) return;
        setData({ lines, names });
        invalidate();
      },
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [invalidate]);

  const geometry = useMemo(() => {
    if (!data) return null;
    const pts: number[] = [];
    for (const f of data.lines.features)
      for (const line of f.geometry.coordinates)
        for (let i = 1; i < line.length; i++) {
          const a = radecToVec(ra360(line[i - 1][0]), line[i - 1][1]);
          const b = radecToVec(ra360(line[i][0]), line[i][1]);
          pts.push(a[0] * R, a[1] * R, a[2] * R, b[0] * R, b[1] * R, b[2] * R);
        }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    return g;
  }, [data]);
  useEffect(() => () => geometry?.dispose(), [geometry]);

  const material = useMemo(() => new THREE.LineBasicMaterial({ color: new THREE.Color(0.86, 0.89, 1), transparent: true, opacity: 0.22, depthWrite: false }), []);
  useEffect(() => () => material.dispose(), [material]);

  // Names: the major (rank 1) constellations, as DOM labels projected each frame.
  const labels = useMemo(
    () =>
      data
        ? data.names.features
            .filter((f) => f.properties.rank === "1")
            .map((f) => ({ name: f.properties.name, pos: new THREE.Vector3(...radecToVec(ra360(f.geometry.coordinates[0]), f.geometry.coordinates[1])).multiplyScalar(R) }))
        : [],
    [data],
  );
  const layer = useRef<HTMLDivElement | null>(null);
  const spans = useRef<HTMLSpanElement[]>([]);
  useEffect(() => {
    const host = gl.domElement.parentElement;
    if (!host || !labels.length) return;
    const div = document.createElement("div");
    div.setAttribute("aria-hidden", "true");
    div.dataset.constellations = "";
    Object.assign(div.style, { position: "absolute", inset: "0", pointerEvents: "none", overflow: "hidden" });
    spans.current = labels.map((l) => {
      const s = document.createElement("span");
      s.textContent = l.name;
      Object.assign(s.style, {
        position: "absolute",
        left: "0",
        top: "0",
        font: "400 11px/1 var(--font-mono)",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: "rgb(220 228 255 / 0.55)",
        whiteSpace: "nowrap",
        willChange: "transform",
      });
      div.appendChild(s);
      return s;
    });
    host.appendChild(div);
    layer.current = div;
    invalidate();
    return () => {
      div.remove();
      layer.current = null;
      spans.current = [];
    };
  }, [gl, labels, invalidate]);

  const v = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ camera, size }) => {
    const div = layer.current;
    if (!div) return;
    div.style.display = visible ? "" : "none";
    if (!visible) return;
    labels.forEach((l, i) => {
      const s = spans.current[i];
      if (!s) return;
      v.copy(l.pos).project(camera);
      const on = v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05;
      s.style.display = on ? "" : "none";
      if (on) s.style.transform = `translate(${((v.x + 1) / 2) * size.width}px, ${((1 - v.y) / 2) * size.height}px) translate(-50%, -50%)`;
    });
  });

  if (!geometry) return null;
  return <lineSegments geometry={geometry} material={material} visible={visible} renderOrder={0} frustumCulled={false} />;
}
