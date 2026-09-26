"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import CameraControls from "camera-controls";
import type { SkyEvent } from "@/lib/contract";
import type { MapData } from "@/lib/data";
import type { HostIndex } from "@/lib/hosts";
import { CATEGORY_STYLE, SHAPE_INDEX } from "@/lib/eventStyle";
import { buildMarkers, type Marker } from "@/lib/markers";
import { TEX_H, TEX_W } from "@/lib/skyTexture";
import { formatDec, formatRa, radecToVec, vecToRadec, type Vec3 } from "@/lib/sky";
import { useStore, type Layers, type StarRef, type State } from "@/state/store";
import { bubbleVertex, eventFragment, eventVertex, skyFragment, skyVertex } from "./shaders";
import { BASE_FOV, capUniform, displayRadius, EVENT_R, hud, MIN_DIST, MIN_FOV, SKY_R, tokenColor, view } from "./constants";
import { leavers, stepFade } from "./markerFade";
import { QUALITY_DESKTOP, QUALITY_PHONE, SkyBaker } from "./skyBake";
import { applyLimits, createRig, currentPose, flyTo, interrupt, stepFlight, type Rig } from "./rig";
import type { Pose, V3 } from "./flight";
import { CatalogStars, CloseUp, createStarUniforms, Hosts, Sun, type StarUniforms } from "./stars";

type SceneProps = {
  data: MapData;
  index: HostIndex;
  /** Events matching the filters (the map shows exactly what the feed lists). */
  events: SkyEvent[];
  /** "Now" for recency and the Sun's position (the recording's end in mock mode). */
  now: number;
  showFps: boolean;
  /** Test hook: skip the zoomed detail re-bake, for before/after comparisons. */
  noDetail?: boolean;
};

function isPhone() {
  return window.matchMedia("(max-width: 899px), (pointer: coarse)").matches;
}
function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** The view from Earth toward (ra, dec): stand just behind Earth and look through it. */
export function earthView(ra: number, dec: number, fov: number): Pose {
  const [x, y, z] = radecToVec(ra, dec);
  return { pos: [-x * MIN_DIST, -y * MIN_DIST, -z * MIN_DIST], target: [0, 0, 0], fov: Math.max(MIN_FOV, Math.min(BASE_FOV, fov)) };
}

/**
 * Opening view: from Earth toward Taurus, Orion and Gemini. Bright, colourful stars (Betelgeuse,
 * Rigel, Aldebaran, the Pleiades, Capella, Sirius) and most of the week's events are in frame.
 */
const HOME: Pose = earthView(75, 8, BASE_FOV);

function SkyShell({
  data,
  layers,
  baker,
  drift,
  selected,
}: {
  data: MapData;
  layers: Layers;
  baker: SkyBaker;
  drift: boolean;
  selected: SkyEvent | null;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const gl = useThree((s) => s.gl);
  const texture = useMemo(() => {
    const t = new THREE.DataTexture(data.skyTexture, TEX_W, TEX_H, THREE.RGBAFormat);
    t.wrapS = THREE.RepeatWrapping;
    t.magFilter = THREE.LinearFilter;
    t.minFilter = THREE.LinearFilter;
    t.generateMipmaps = false;
    t.needsUpdate = true;
    return t;
  }, [data.skyTexture]);
  useEffect(() => () => texture.dispose(), [texture]);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: skyVertex,
        fragmentShader: skyFragment,
        side: THREE.BackSide,
        depthWrite: false,
        uniforms: {
          uTex: { value: texture },
          uCubeBase: { value: baker.cubeBase.texture },
          uCubeGlow: { value: baker.cubeGlow.texture },
          uDetailBase: { value: baker.detailBase.texture },
          uDetailGlow: { value: baker.detailGlow.texture },
          uDetailVP: { value: baker.detailVP },
          uDetailOn: { value: 0 },
          uBaked: { value: 0 },
          uArt: { value: 0 },
          uTime: { value: 0 },
          uDrift: { value: 0 },
          uZone: { value: 1 },
          uHeat: { value: 0 },
          uSel: { value: new THREE.Vector4() },
          uSelOn: { value: 0 },
          cDeep: { value: tokenColor("--space", "#000000") },
          cGrid: { value: tokenColor("--grid", "#1f2127") },
          cRubin: { value: tokenColor("--rubin", "#6fd6c6") },
          cAccent: { value: tokenColor("--accent", "#a3b8ff") },
          cHeatHi: { value: tokenColor("--ink", "#f4f4f5") },
        },
      }),
    [texture, baker],
  );
  useEffect(() => () => material.dispose(), [material]);

  useEffect(() => {
    const u = material.uniforms;
    u.uZone.value = layers.coverage ? 1 : 0;
    u.uHeat.value = layers.heatmap ? 1 : 0;
    u.uArt.value = layers.art ? 1 : 0;
    u.uDrift.value = drift ? 1 : 0;
    // The selected event's error circle, when it is big enough to see (more than about 1 arcminute).
    const loc = selected?.location;
    const on = loc?.frame === "sky" && loc.error_deg > 0.02;
    u.uSelOn.value = on ? 1 : 0;
    if (on) capUniform(loc.ra_deg, loc.dec_deg, loc.error_deg, u.uSel.value);
    invalidate();
  }, [layers, drift, selected, material, invalidate]);

  useFrame(({ clock }) => {
    // Bake the illustrated sky progressively, one cube face per frame, only once the layer is on.
    if (layers.art && material.uniforms.uBaked.value < 1) {
      if (baker.bakeStep(gl)) {
        material.uniforms.uBaked.value = 1;
        view.bakeInfo = { cubeMs: Math.round(baker.lastBakeMs), detailMs: 0, detailBakes: 0, face: baker.quality.face };
      }
      invalidate();
    }
    material.uniforms.uTime.value = clock.elapsedTime;
    material.uniforms.uDetailOn.value = baker.detailOn ? 1 : 0;
    // Render targets can be re-created on resize: keep the uniforms pointing at the live textures.
    material.uniforms.uDetailBase.value = baker.detailBase.texture;
    material.uniforms.uDetailGlow.value = baker.detailGlow.texture;
  });

  return (
    <mesh material={material} renderOrder={-1} frustumCulled={false}>
      <sphereGeometry args={[SKY_R, 96, 48]} />
    </mesh>
  );
}

/** Uniforms the scene animates for event markers. */
function createEventUniforms() {
  return { uHover: { value: -1 }, uHoverT: { value: 0 }, uSelected: { value: -1 }, uDim: { value: 0 }, uTime: { value: 0 }, uPulse: { value: 0 } };
}
type EventUniforms = ReturnType<typeof createEventUniforms>;

/**
 * One marker per event: category colour and shape, prominence by recency. Always drawn on top.
 * `markers` is the live set followed by leavers (from `live` on), which fade out and cannot be picked;
 * new markers fade in. Opacity carries over by id when the set changes mid-fade.
 */
function EventMarkers({
  markers,
  live,
  uniforms,
  positionsRef,
  reduced,
  onFaded,
}: {
  markers: Marker[];
  live: number;
  uniforms: EventUniforms;
  positionsRef: React.RefObject<Float32Array | null>;
  reduced: boolean;
  onFaded: () => void;
}) {
  const dpr = useThree((s) => s.viewport.dpr);
  const invalidate = useThree((s) => s.invalidate);
  // Fade progress (0..1) by event id, carried across marker-set changes.
  const [fade] = useState(() => new Map<string, number>());
  const geometry = useMemo(() => {
    const n = markers.length;
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    const shape = new Float32Array(n);
    const rec = new Float32Array(n);
    const fresh = new Float32Array(n);
    const idx = new Float32Array(n);
    const alpha = new Float32Array(n);
    const colors = new Map<string, THREE.Color>();
    markers.forEach((m, i) => {
      const [x, y, z] = radecToVec(m.ra, m.dec);
      pos.set([x * EVENT_R, y * EVENT_R, z * EVENT_R], i * 3);
      const st = CATEGORY_STYLE[m.category];
      if (!colors.has(st.token)) colors.set(st.token, tokenColor(st.token, st.fallback));
      const c = colors.get(st.token)!;
      col.set([c.r, c.g, c.b], i * 3);
      shape[i] = SHAPE_INDEX[st.shape];
      rec[i] = m.recency;
      fresh[i] = m.fresh ? 1 : 0;
      idx[i] = i;
      alpha[i] = fade.get(m.id) ?? 0;
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aColor", new THREE.BufferAttribute(col, 3));
    g.setAttribute("aShape", new THREE.BufferAttribute(shape, 1));
    g.setAttribute("aRecency", new THREE.BufferAttribute(rec, 1));
    g.setAttribute("aFresh", new THREE.BufferAttribute(fresh, 1));
    g.setAttribute("aIndex", new THREE.BufferAttribute(idx, 1));
    g.setAttribute("aAlpha", new THREE.BufferAttribute(alpha, 1));
    return g;
  }, [markers, fade]);
  // Linear fade progress per marker; the eased opacity goes to aAlpha.
  const progress = useMemo(() => Float32Array.from(markers, (m) => fade.get(m.id) ?? 0), [markers, fade]);
  useEffect(() => {
    // Pick only live markers: leavers get NaN positions, which never win the nearest-marker test.
    const pos = geometry.getAttribute("position").array as Float32Array;
    const pick = pos.slice();
    pick.fill(NaN, live * 3);
    positionsRef.current = pick;
    return () => geometry.dispose();
  }, [geometry, positionsRef, live]);
  const faded = useRef(false);
  const settled = useRef(false);
  useEffect(() => {
    faded.current = false;
    settled.current = false;
    invalidate();
  }, [geometry, invalidate]);
  useFrame((_, dt) => {
    // Once every marker has arrived, stop touching the buffer (the loop may still run for the pulse).
    if (settled.current) return;
    const attr = geometry.getAttribute("aAlpha") as THREE.BufferAttribute;
    const alpha = attr.array as Float32Array;
    const moving = stepFade(progress, alpha, live, dt, reduced);
    attr.needsUpdate = true;
    markers.forEach((m, i) => fade.set(m.id, progress[i]));
    if (moving) invalidate();
    else if (markers.length === live) settled.current = true;
    else if (!faded.current) {
      faded.current = true;
      for (const m of markers.slice(live)) fade.delete(m.id);
      onFaded();
    }
  });
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: eventVertex,
        fragmentShader: eventFragment,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        uniforms: { ...uniforms, uPx: { value: 1 }, cAccent: { value: tokenColor("--accent", "#a3b8ff") } },
      }),
    [uniforms],
  );
  useEffect(() => () => material.dispose(), [material]);
  material.uniforms.uPx.value = dpr;
  return <points geometry={geometry} material={material} frustumCulled={false} renderOrder={6} />;
}

function Earth() {
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: bubbleVertex,
        transparent: true,
        uniforms: { uOpacity: { value: 1 } },
        fragmentShader: /* glsl */ `
          precision mediump float;
          uniform float uOpacity;
          varying vec3 vN;
          varying vec3 vV;
          void main() {
            float ndv = abs(dot(normalize(vN), normalize(vV)));
            vec3 body = mix(vec3(0.07, 0.08, 0.1), vec3(0.2, 0.22, 0.27), ndv);
            vec3 rim = vec3(0.64, 0.72, 1.0) * pow(1.0 - ndv, 3.0) * 0.8;
            // Tuned as display values: decode to linear, since the composer encodes to sRGB on output.
            gl_FragColor = vec4(pow(body + rim, vec3(2.2)), uOpacity);
          }
        `,
      }),
    [],
  );
  const mesh = useRef<THREE.Mesh>(null);
  useFrame(({ camera }) => {
    // Fade Earth out as the camera arrives at it: from there you are looking at the sky from Earth.
    const d = camera.position.length();
    const o = THREE.MathUtils.smoothstep(d, 1.4, 4);
    material.uniforms.uOpacity.value = o;
    if (mesh.current) mesh.current.visible = o > 0.01;
  });
  return (
    <mesh ref={mesh} material={material} renderOrder={3}>
      <sphereGeometry args={[0.5, 32, 16]} />
    </mesh>
  );
}

function hostPos(positionsRef: React.RefObject<Float32Array | null>, i: number): V3 | null {
  const p = positionsRef.current;
  return p ? [p[i * 3], p[i * 3 + 1], p[i * 3 + 2]] : null;
}

/**
 * Owns camera-controls and runs every camera change: fly-to flights, the eased field of view, the
 * host close-up (enter, switch, leave), the adaptive near plane, marker/host highlight fades, and
 * the zoomed detail re-bake once the view settles.
 */
function Director({
  rig,
  index,
  data,
  hostPositions,
  starUniforms,
  eventUniforms,
  baker,
  noDetail,
}: {
  rig: Rig;
  index: HostIndex;
  data: MapData;
  hostPositions: React.RefObject<Float32Array | null>;
  starUniforms: StarUniforms;
  eventUniforms: EventUniforms;
  baker: SkyBaker;
  noDetail: boolean;
}) {
  const { state } = useStore();
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const gl = useThree((s) => s.gl);
  const size = useThree((s) => s.size);
  const invalidate = useThree((s) => s.invalidate);

  const controls = useMemo(() => {
    const c = new CameraControls(camera, gl.domElement);
    const A = CameraControls.ACTION;
    // Zoom is ours (dolly toward Earth, then narrow the field): camera-controls only rotates.
    c.mouseButtons.left = A.ROTATE;
    c.mouseButtons.middle = A.NONE;
    c.mouseButtons.right = A.NONE;
    c.mouseButtons.wheel = A.NONE;
    c.touches.one = A.TOUCH_ROTATE;
    c.touches.two = A.NONE;
    c.touches.three = A.NONE;
    c.smoothTime = rig.reduced ? 0 : 0.22;
    c.draggingSmoothTime = rig.reduced ? 0 : 0.1;
    c.restThreshold = 0.0005;
    c.setLookAt(...HOME.pos, ...HOME.target, false);
    return c;
  }, [camera, gl, rig.reduced]);

  useEffect(() => {
    rig.controls = controls;
    rig.camera = camera;
    camera.fov = HOME.fov;
    camera.updateProjectionMatrix();
    const wake = () => invalidate();
    const stop = () => interrupt(rig);
    controls.addEventListener("control", wake);
    controls.addEventListener("controlstart", stop);
    controls.addEventListener("transitionstart", wake);
    applyLimits(rig);
    return () => {
      controls.removeEventListener("control", wake);
      controls.removeEventListener("controlstart", stop);
      controls.removeEventListener("transitionstart", wake);
      controls.dispose();
      rig.controls = null;
    };
  }, [controls, camera, rig, invalidate]);

  // Host close-up: fly into the selected host, between hosts, or back out when it is closed.
  const prevSel = useRef<number | null>(null);
  const stateRef = useRef<State>(state);
  useEffect(() => {
    stateRef.current = state;
  });
  // Host close-up for planet hosts; bright catalogue stars are centred from Earth (they have no 3D place).
  const sel = state.selectedStar?.kind === "host" ? state.selectedStar.i : null;
  const selBright = state.selectedStar?.kind === "bright" ? state.selectedStar.i : null;
  const trueScale = state.trueScale;
  useEffect(() => {
    const prev = prevSel.current;
    prevSel.current = sel;
    if (!rig.controls || !rig.camera) return;
    const s = stateRef.current;
    if (sel !== null) {
      const p = hostPos(hostPositions, sel);
      if (!p) return;
      if (prev === null) rig.saved = rig.flight?.kind === "back" ? rig.flight.to : currentPose(rig);
      const R = displayRadius(index.hosts.rad?.[sel] ?? 0);
      // Arrive from the side the camera is already on, a few stellar radii out. On a portrait screen
      // the width is the tighter field, so stand further back to keep the whole disc in view.
      const cam = rig.camera.position;
      const dir = new THREE.Vector3(cam.x - p[0], cam.y - p[1], cam.z - p[2]);
      if (dir.lengthSq() < 1e-20) dir.set(0, 0, 1);
      dir.normalize().multiplyScalar(R * 3.6 * Math.max(1, 0.85 / rig.camera.aspect));
      rig.limits = { min: R * 1.25, max: s.trueScale ? 700 : 320 };
      flyTo(rig, { pos: [p[0] + dir.x, p[1] + dir.y, p[2] + dir.z], target: p, fov: BASE_FOV }, "focus");
      rig.selectedT = 0;
      starUniforms.uSelected.value = sel;
    } else if (prev !== null) {
      rig.limits = { min: 0.3, max: s.trueScale ? 700 : 320 };
      starUniforms.uSelected.value = -1;
      if (rig.flight?.kind === "jump") return;
      const to = rig.saved ?? HOME;
      rig.saved = null;
      flyTo(rig, to, "back");
    }
    invalidate();
  }, [sel, trueScale, rig, index, hostPositions, starUniforms, invalidate]);

  useEffect(() => {
    if (selBright === null || !rig.controls) return;
    flyTo(rig, earthView(data.sky.stars.ra[selBright], data.sky.stars.dec[selBright], 12), "jump");
    invalidate();
  }, [selBright, rig, data.sky.stars, invalidate]);

  useEffect(() => {
    if (sel === null) rig.limits = { min: 0.3, max: trueScale ? 700 : 320 };
    if (!rig.flight && rig.controls) applyLimits(rig);
  }, [trueScale, sel, rig]);

  const art = state.layers.art;
  const focusPos = useMemo(() => new THREE.Vector3(), []);
  const settle = useRef({ quietFor: 0, dirty: true });
  let lastFov = -1;
  useFrame((_, dt) => {
    const step = Math.min(dt, 0.1);
    if (!rig.reduced) rig.time += step;
    // Fresh-event pulse: runs on the same clock; none under reduced motion.
    eventUniforms.uTime.value = rig.time;
    eventUniforms.uPulse.value = rig.reduced ? 0 : 1;
    let busy = stepFlight(rig, performance.now());

    // Ease the field of view toward its target (zooming past Earth narrows the field).
    if (!rig.flight && Math.abs(camera.fov - rig.fovTarget) > 1e-4) {
      camera.fov = rig.reduced ? rig.fovTarget : camera.fov + (rig.fovTarget - camera.fov) * (1 - Math.exp(-step / 0.07));
      if (Math.abs(camera.fov - rig.fovTarget) < 1e-3) camera.fov = rig.fovTarget;
      camera.updateProjectionMatrix();
      busy = true;
    }
    controls.azimuthRotateSpeed = controls.polarRotateSpeed = 0.5 * (camera.fov / BASE_FOV);
    if (controls.update(step)) busy = true;

    // Near plane follows a focused host, so a 0.1 R☉ dwarf a few radii away is never clipped.
    const p = sel !== null ? hostPos(hostPositions, sel) : null;
    const near = p ? THREE.MathUtils.clamp(camera.position.distanceTo(focusPos.set(...p)) * 0.05, 1e-6, 0.05) : 0.05;
    if (Math.abs(camera.near - near) > near * 0.05) {
      camera.near = near;
      camera.updateProjectionMatrix();
    }

    // Hover and selection rings fade in over 120 to 150 ms (instant under reduced motion).
    const hoverGoal = rig.hover >= 0 ? 1 : 0;
    if (rig.hover >= 0) starUniforms.uHover.value = rig.hover;
    if (rig.hoverT !== hoverGoal) {
      rig.hoverT = rig.reduced ? hoverGoal : THREE.MathUtils.clamp(rig.hoverT + (hoverGoal ? 1 : -1) * (step / 0.12), 0, 1);
      busy = true;
    }
    if (rig.hoverT === 0 && rig.hover < 0) starUniforms.uHover.value = -1;
    starUniforms.uHoverT.value = rig.hoverT;
    if (rig.selectedT < 1) {
      rig.selectedT = rig.reduced ? 1 : Math.min(1, rig.selectedT + step / 0.15);
      busy = true;
    }
    starUniforms.uSelectedT.value = rig.selectedT;
    const evGoal = eventUniforms.uHover.value >= 0 ? 1 : 0;
    if (eventUniforms.uHoverT.value !== evGoal) {
      eventUniforms.uHoverT.value = rig.reduced ? evGoal : THREE.MathUtils.clamp(eventUniforms.uHoverT.value + (evGoal ? 1 : -1) * (step / 0.12), 0, 1);
      busy = true;
    }

    if (hud.fov && camera.fov !== lastFov) {
      lastFov = camera.fov;
      hud.fov.textContent = `${camera.fov < 10 ? camera.fov.toFixed(1) : Math.round(camera.fov)}°`;
    }

    // Zoomed detail: once the view has been still for 250 ms, re-bake a sharp patch of the
    // illustrated sky for exactly this view (only when that layer is on and the field is narrow).
    const s = settle.current;
    if (busy) {
      s.quietFor = 0;
      s.dirty = true;
    } else {
      s.quietFor += step;
      if (s.dirty && s.quietFor > 0.25) {
        s.dirty = false;
        if (art && baker.cubeBase && camera.fov < 25 && !noDetail) {
          baker.bakeDetail(gl, camera, size.width, size.height);
          if (view.bakeInfo) {
            view.bakeInfo.detailMs = Math.round(baker.lastDetailMs * 10) / 10;
            view.bakeInfo.detailBakes++;
          }
        } else {
          baker.detailOn = false;
        }
        invalidate();
      }
    }
    if (busy) invalidate();
  }, -1);

  // Switching the illustrated layer on (or resizing) needs a fresh detail patch.
  useEffect(() => {
    settle.current.dirty = true;
    settle.current.quietFor = 0;
    invalidate();
  }, [art, size.width, size.height, invalidate]);

  return null;
}

/**
 * All pointer input on the canvas: hover and pick an event (or a planet host, with that layer on),
 * pinch and wheel zoom, and the pointer's RA/Dec for the status bar.
 */
function Input({
  index,
  data,
  markers,
  eventPositions,
  hostPositions,
  brightPositions,
  brightUniforms,
  rig,
  eventUniforms,
  onPickEvent,
}: {
  index: HostIndex;
  data: MapData;
  markers: Marker[];
  eventPositions: React.RefObject<Float32Array | null>;
  hostPositions: React.RefObject<Float32Array | null>;
  brightPositions: React.RefObject<Float32Array | null>;
  brightUniforms: StarUniforms;
  rig: Rig;
  eventUniforms: EventUniforms;
  onPickEvent: (id: string) => void;
}) {
  const { state, dispatch } = useStore();
  const gl = useThree((s) => s.gl);
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const invalidate = useThree((s) => s.invalidate);
  const live = useRef({ selStar: state.selectedStar, hosts: state.layers.hosts, stars: state.layers.stars, markers, onPickEvent });
  useEffect(() => {
    live.current = { selStar: state.selectedStar, hosts: state.layers.hosts, stars: state.layers.stars, markers, onPickEvent };
  }, [state.selectedStar, state.layers.hosts, state.layers.stars, markers, onPickEvent]);

  useEffect(() => {
    const el = gl.domElement;
    const raycaster = new THREE.Raycaster();
    const pointers = new Map<number, { x: number; y: number }>();
    let tap: { x: number; y: number } | null = null;
    let pinch = 0;
    let hoverRaf = 0;

    const zoomBy = (f: number) => {
      const c = rig.controls;
      if (!c) return;
      interrupt(rig);
      const smooth = !rig.reduced;
      const dist = c.getSpherical(new THREE.Spherical(), true).radius;
      if (live.current.selStar?.kind === "host") {
        // Close-up: dolly toward the star, down to just above its surface.
        c.dollyTo(THREE.MathUtils.clamp(dist * f, rig.limits.min, rig.limits.max), smooth);
      } else if (f < 1) {
        if (dist > MIN_DIST * 1.001) c.dollyTo(Math.max(MIN_DIST, dist * f), smooth);
        else rig.fovTarget = Math.max(MIN_FOV, rig.fovTarget * f);
      } else {
        if (rig.fovTarget < BASE_FOV * 0.999) rig.fovTarget = Math.min(BASE_FOV, rig.fovTarget * f);
        else c.dollyTo(Math.min(rig.limits.max, dist * f), smooth);
      }
      invalidate();
    };

    view.project = (ra, dec) => {
      const [x, y, z] = radecToVec(ra, dec);
      const v = new THREE.Vector3(x * EVENT_R, y * EVENT_R, z * EVENT_R).project(camera);
      if (v.z > 1) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left + ((v.x + 1) / 2) * r.width, y: r.top + ((1 - v.y) / 2) * r.height };
    };

    view.jumpTo = (ra, dec, fovDeg) => {
      flyTo(rig, earthView(ra, dec, fovDeg), "jump");
      if (live.current.selStar !== null) dispatch({ type: "selectStar", star: null });
      invalidate();
    };

    const skyDir = (clientX: number, clientY: number): Vec3 => {
      const rect = el.getBoundingClientRect();
      const ndc = new THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(ndc, camera);
      const o = raycaster.ray.origin;
      const d = raycaster.ray.direction;
      const b = o.dot(d);
      const c = o.lengthSq() - SKY_R * SKY_R;
      const t = -b + Math.sqrt(Math.max(0, b * b - c));
      const p = o.clone().addScaledVector(d, t).normalize();
      return [p.x, p.y, p.z];
    };

    /** Nearest point of `pos` to a screen point within `maxPx`, or -1. */
    const nearest = (pos: Float32Array | null, clientX: number, clientY: number, maxPx: number) => {
      if (!pos) return -1;
      const rect = el.getBoundingClientRect();
      const v = new THREE.Vector3();
      let best = -1;
      let bestD = maxPx;
      for (let i = 0; i < pos.length / 3; i++) {
        v.set(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]).project(camera);
        if (v.z > 1 || v.z < -1) continue;
        const d = Math.hypot(((v.x + 1) / 2) * rect.width - (clientX - rect.left), ((1 - v.y) / 2) * rect.height - (clientY - rect.top));
        if (d < bestD) {
          bestD = d;
          best = i;
        }
      }
      return best;
    };

    /** Events first (they are on top); hosts only with their layer on. */
    type Hit = { kind: "event" | "host" | "bright"; i: number };
    /** Events first (drawn on top), then planet hosts, then bright stars: every visible star is clickable. */
    const pick = (x: number, y: number, px: number): Hit | null => {
      const e = nearest(eventPositions.current, x, y, px);
      if (e >= 0) return { kind: "event", i: e };
      if (live.current.hosts) {
        const h = nearest(hostPositions.current, x, y, px);
        if (h >= 0) return { kind: "host", i: h };
      }
      if (live.current.stars) {
        const b = nearest(brightPositions.current, x, y, px);
        if (b >= 0) {
          // A bright star that is also a planet host opens as the host (with its close-up).
          const h = data.bright.host[b];
          return h >= 0 && live.current.hosts ? { kind: "host", i: h } : { kind: "bright", i: b };
        }
      }
      return null;
    };

    const setHover = (hit: Hit | null) => {
      const evI = hit?.kind === "event" ? hit.i : -1;
      const hoI = hit?.kind === "host" ? hit.i : -1;
      const brI = hit?.kind === "bright" ? hit.i : -1;
      if (evI === eventUniforms.uHover.value && hoI === rig.hover && brI === rig.hoverBright) return;
      rig.hoverBright = brI;
      brightUniforms.uHover.value = brI;
      brightUniforms.uHoverT.value = brI >= 0 ? 1 : 0;
      if (evI >= 0) eventUniforms.uHoverT.value = 0;
      eventUniforms.uHover.value = evI;
      if (hoI >= 0 && rig.hover >= 0) rig.hoverT = 0;
      rig.hover = hoI;
      el.style.cursor = hit ? "pointer" : "";
      if (hud.hover) {
        hud.hover.textContent =
          evI >= 0 ? live.current.markers[evI].title : hoI >= 0 ? index.hosts.name[hoI] : brI >= 0 ? data.bright.name[brI] || "Unnamed star" : "";
        hud.hover.dataset.kind = hit?.kind ?? "";
      }
      invalidate();
    };

    const down = (e: PointerEvent) => {
      interrupt(rig);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = Math.hypot(a.x - b.x, a.y - b.y);
        tap = null;
        return;
      }
      if (pointers.size > 2 || e.button !== 0) return;
      tap = { x: e.clientX, y: e.clientY };
    };

    const move = (e: PointerEvent) => {
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2 && pinch > 0) {
        const [a, b] = [...pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (dist > 0) zoomBy(pinch / dist);
        pinch = dist;
        return;
      }
      if (e.pointerType !== "mouse") return;
      if (hud.pointer) {
        const { ra, dec } = vecToRadec(skyDir(e.clientX, e.clientY));
        hud.pointer.textContent = `${formatRa(ra)}  ${formatDec(dec)}`;
      }
      if (e.buttons === 0 && !hoverRaf) {
        const x = e.clientX;
        const y = e.clientY;
        hoverRaf = requestAnimationFrame(() => {
          hoverRaf = 0;
          setHover(pick(x, y, 14));
        });
      }
    };

    const up = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = 0;
      if (tap && Math.hypot(e.clientX - tap.x, e.clientY - tap.y) < 6) {
        // A tap on empty sky does nothing, so a stray tap never closes what you are reading.
        const hit = pick(e.clientX, e.clientY, e.pointerType === "mouse" ? 14 : 24);
        if (hit?.kind === "event") live.current.onPickEvent(live.current.markers[hit.i].id);
        else if (hit) {
          const star: StarRef = { kind: hit.kind === "host" ? "host" : "bright", i: hit.i };
          const cur = live.current.selStar;
          if (!cur || cur.kind !== star.kind || cur.i !== star.i) dispatch({ type: "selectStar", star });
        }
      }
      tap = null;
    };

    const cancel = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = 0;
    };

    const leave = () => setHover(null);

    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomBy(Math.exp(Math.max(-60, Math.min(60, e.deltaY)) * 0.004));
    };

    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", cancel);
    el.addEventListener("pointerleave", leave);
    el.addEventListener("wheel", wheel, { passive: false });
    return () => {
      cancelAnimationFrame(hoverRaf);
      view.jumpTo = null;
      view.project = null;
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", cancel);
      el.removeEventListener("pointerleave", leave);
      el.removeEventListener("wheel", wheel);
    };
  }, [gl, camera, dispatch, index, data, eventPositions, hostPositions, brightPositions, brightUniforms, rig, eventUniforms, invalidate]);

  return null;
}

/** Keeps DOM labels beside what they name: the hovered event or host, Earth and the Sun. */
function Anchors({
  rig,
  eventUniforms,
  eventPositions,
  hostPositions,
  brightPositions,
  sun,
}: {
  rig: Rig;
  eventUniforms: EventUniforms;
  eventPositions: React.RefObject<Float32Array | null>;
  hostPositions: React.RefObject<Float32Array | null>;
  brightPositions: React.RefObject<Float32Array | null>;
  sun: { ra: number; dec: number };
}) {
  const v = useMemo(() => new THREE.Vector3(), []);
  const sunPos = useMemo(() => {
    const [x, y, z] = radecToVec(sun.ra, sun.dec);
    return new THREE.Vector3(x * EVENT_R, y * EVENT_R, z * EVENT_R);
  }, [sun]);
  useFrame(({ camera, size }) => {
    const place = (el: HTMLElement | null, p: THREE.Vector3 | null, dx: number, dy: number, extra = true) => {
      if (!el) return;
      if (!p || !extra) {
        el.dataset.visible = "false";
        return;
      }
      v.copy(p).project(camera);
      const x = ((v.x + 1) / 2) * size.width;
      const y = ((1 - v.y) / 2) * size.height;
      const onScreen = v.z < 1 && Math.abs(v.x) < 1.02 && Math.abs(v.y) < 1.02;
      el.style.transform = `translate(${(x + dx).toFixed(1)}px, ${(y + dy).toFixed(1)}px)`;
      el.dataset.visible = onScreen ? "true" : "false";
    };
    const ev = eventUniforms.uHover.value;
    const ep = eventPositions.current;
    const hp = rig.hover >= 0 ? hostPos(hostPositions, rig.hover) : rig.hoverBright >= 0 ? hostPos(brightPositions, rig.hoverBright) : null;
    const target = ev >= 0 && ep ? new THREE.Vector3(ep[ev * 3], ep[ev * 3 + 1], ep[ev * 3 + 2]) : hp ? new THREE.Vector3(...hp) : null;
    place(hud.hover, target, 16, -10);
    // Earth is only visible once you zoom out past it; say what it is.
    place(hud.earth, new THREE.Vector3(0, 0.62, 0), -18, -26, camera.position.length() > 4);
    place(hud.sun, sunPos, 14, 14);
  });
  return null;
}

function FpsMeter() {
  const frames = useRef(0);
  const last = useRef(0);
  useFrame(() => {
    frames.current++;
    const now = performance.now();
    if (!last.current) last.current = now;
    if (now - last.current >= 1000) {
      if (hud.fps) hud.fps.textContent = `${Math.round((frames.current * 1000) / (now - last.current))} fps`;
      frames.current = 0;
      last.current = now;
    }
  });
  return null;
}

/** Frame loop: continuous while something animates, on demand otherwise, and stopped while the tab is hidden. */
function Loop({ want }: { want: "always" | "demand" }) {
  const setFrameloop = useThree((s) => s.setFrameloop);
  useEffect(() => {
    const apply = () => setFrameloop(document.hidden ? "never" : want);
    apply();
    document.addEventListener("visibilitychange", apply);
    return () => document.removeEventListener("visibilitychange", apply);
  }, [want, setFrameloop]);
  return null;
}

function Invalidator({ deps }: { deps: unknown[] }) {
  const invalidate = useThree((s) => s.invalidate);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => invalidate(), deps);
  return null;
}

export default function Scene({ data, index, events, now, showFps, noDetail = false }: SceneProps) {
  const { state, dispatch } = useStore();
  const phone = useMemo(() => isPhone(), []);
  const reduced = useMemo(() => reducedMotion(), []);
  const rig = useMemo(() => createRig(reduced, BASE_FOV), [reduced]);
  const baker = useMemo(() => new SkyBaker(data.sky, phone ? QUALITY_PHONE : QUALITY_DESKTOP), [data.sky, phone]);
  useEffect(() => () => baker.dispose(), [baker]);
  // The nebula layer drifts only on desktop, with motion allowed and the layer on.
  const drift = !phone && !reduced && state.layers.art;
  // A focused host's surface is alive unless motion is reduced; then it is a still image.
  const living = state.selectedStar?.kind === "host" && !reduced;
  // Events from the last 24 hours pulse, which needs a running frame loop (not under reduced motion).
  const pulsing = !reduced && events.some((e) => e.location.frame !== "earth" && now - Date.parse(e.observed_at) < 24 * 3600_000);

  return (
    <Canvas
      dpr={[1, 2]}
      frameloop="demand"
      camera={{ fov: BASE_FOV, near: 0.05, far: 5000, position: HOME.pos }}
      gl={{ antialias: false, powerPreference: "high-performance" }}
      onCreated={({ gl }) => gl.setClearColor(tokenColor("--space", "#000000"))}
      aria-hidden="true"
    >
      <Loop want={showFps || drift || living || pulsing ? "always" : "demand"} />
      <SceneContent data={data} index={index} events={events} now={now} baker={baker} drift={drift} rig={rig} phone={phone} noDetail={noDetail} dispatch={dispatch} />
      <EffectComposer multisampling={phone ? 0 : 4}>
        {/* Threshold above everything but star cores and the close-up star: the sky itself never glows. */}
        <Bloom mipmapBlur luminanceThreshold={1.0} luminanceSmoothing={0.12} intensity={0.75} radius={0.45} levels={phone ? 5 : 6} resolutionScale={phone ? 0.5 : 1} />
      </EffectComposer>
      {showFps && <FpsMeter />}
    </Canvas>
  );
}

function SceneContent({
  data,
  index,
  events,
  now,
  baker,
  drift,
  rig,
  phone,
  noDetail,
  dispatch,
}: {
  data: MapData;
  index: HostIndex;
  events: SkyEvent[];
  now: number;
  baker: SkyBaker;
  drift: boolean;
  rig: Rig;
  phone: boolean;
  noDetail: boolean;
  dispatch: ReturnType<typeof useStore>["dispatch"];
}) {
  const { state } = useStore();
  const hostPositions = useRef<Float32Array | null>(null);
  const eventPositions = useRef<Float32Array | null>(null);
  const brightPositions = useRef<Float32Array | null>(null);
  const brightUniforms = useMemo(() => createStarUniforms(), []);
  const starUniforms = useMemo(() => createStarUniforms(), []);
  const eventUniforms = useMemo(() => createEventUniforms(), []);
  const { markers, sun } = useMemo(() => buildMarkers(events, now), [events, now]);
  // Markers the filters just removed keep fading out after the live ones (see EventMarkers).
  const [prevMarkers, setPrevMarkers] = useState(markers);
  const [leaving, setLeaving] = useState<Marker[]>([]);
  if (prevMarkers !== markers) {
    setPrevMarkers(markers);
    setLeaving(rig.reduced ? [] : leavers(prevMarkers, leaving, markers));
  }
  const drawn = useMemo(() => (leaving.length ? [...markers, ...leaving] : markers), [markers, leaving]);
  const dropLeavers = useMemo(() => () => setLeaving([]), []);
  const selected = useMemo(() => events.find((e) => e.id === state.selectedEvent) ?? null, [events, state.selectedEvent]);

  // Feed hover and the selection highlight their markers; others dim a little while one is selected.
  useEffect(() => {
    const idOf = (id: string | null) => (id ? markers.findIndex((m) => m.id === id) : -1);
    eventUniforms.uSelected.value = idOf(state.selectedEvent);
    eventUniforms.uDim.value = state.selectedEvent && idOf(state.selectedEvent) >= 0 ? 1 : 0;
    const h = idOf(state.hoverEvent);
    if (h >= 0) {
      eventUniforms.uHover.value = h;
      if (hud.hover) hud.hover.textContent = markers[h].title;
      eventUniforms.uHoverT.value = rig.reduced ? 1 : 0;
    } else if (state.hoverEvent === null && eventUniforms.uHover.value >= 0) {
      eventUniforms.uHover.value = -1;
    }
  }, [markers, state.selectedEvent, state.hoverEvent, eventUniforms, rig.reduced]);

  // The selected bright star gets the accent ring.
  useEffect(() => {
    const b = state.selectedStar?.kind === "bright" ? state.selectedStar.i : -1;
    brightUniforms.uSelected.value = b;
    brightUniforms.uSelectedT.value = b >= 0 ? 1 : 0;
  }, [state.selectedStar, brightUniforms]);

  const onPickEvent = useMemo(() => (id: string) => dispatch({ type: "selectEvent", id }), [dispatch]);

  return (
    <>
      <Director rig={rig} index={index} data={data} hostPositions={hostPositions} starUniforms={starUniforms} eventUniforms={eventUniforms} baker={baker} noDetail={noDetail} />
      <SkyShell data={data} layers={state.layers} baker={baker} drift={drift} selected={selected} />
      <CatalogStars data={data} visible={state.layers.stars} dim={state.layers.dimStars} uniforms={brightUniforms} positionsRef={brightPositions} />
      <Sun ra={sun.ra} dec={sun.dec} />
      <Hosts index={index} trueScale={state.trueScale} visible={state.layers.hosts} dim={state.layers.dimStars && state.selectedStar?.kind !== "host"} starUniforms={starUniforms} positionsRef={hostPositions} />
      <CloseUp index={index} selected={state.selectedStar?.kind === "host" ? state.selectedStar.i : null} positionsRef={hostPositions} starUniforms={starUniforms} rig={rig} octaves={phone ? 2 : 4} />
      <Earth />
      <EventMarkers markers={drawn} live={markers.length} uniforms={eventUniforms} positionsRef={eventPositions} reduced={rig.reduced} onFaded={dropLeavers} />
      <Input index={index} data={data} markers={markers} eventPositions={eventPositions} hostPositions={hostPositions} brightPositions={brightPositions} brightUniforms={brightUniforms} rig={rig} eventUniforms={eventUniforms} onPickEvent={onPickEvent} />
      <Anchors rig={rig} eventUniforms={eventUniforms} eventPositions={eventPositions} hostPositions={hostPositions} brightPositions={brightPositions} sun={sun} />
      <Invalidator deps={[state.selectedEvent, state.hoverEvent, state.selectedStar, state.layers, markers]} />
    </>
  );
}
