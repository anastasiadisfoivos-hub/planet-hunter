"use client";

import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import CameraControls from "camera-controls";
import { SPHERE_RADIUS_MAX, SPHERE_RADIUS_MIN, type CatchType, type Sphere } from "@/lib/contract";
import type { MapData } from "@/lib/data";
import { classify, type HostIndex } from "@/lib/classify";
import { bakeFootprint, bakeHeatmap, bakeTonight, TEX_H, TEX_W } from "@/lib/skyTexture";
import { formatDec, formatRa, radecToVec, separationDeg, vecToRadec, type Vec3 } from "@/lib/sky";
import { useStore, type Draft, type Layers, type State, type Watch } from "@/state/store";
import {
  bubbleFragment,
  bubbleVertex,
  markerFragment,
  markerVertex,
  MAX_SHADER_WATCHES,
  skyFragment,
  skyVertex,
} from "./shaders";
import { BASE_FOV, capUniform, displayRadius, hud, MIN_DIST, MIN_FOV, SKY_R, tokenColor, view, WATCH_D } from "./constants";
import { QUALITY_DESKTOP, QUALITY_PHONE, SkyBaker } from "./skyBake";
import { applyLimits, createRig, currentPose, flyTo, interrupt, stepFlight, type Rig } from "./rig";
import type { Pose, V3 } from "./flight";
import { CatalogStars, CloseUp, createStarUniforms, Hosts, type StarUniforms } from "./stars";

type SceneProps = {
  data: MapData;
  index: HostIndex;
  showFps: boolean;
  onHeatMax: (max: number) => void;
};

function isPhone() {
  return window.matchMedia("(max-width: 899px), (pointer: coarse)").matches;
}
function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const OVERVIEW: Pose = { pos: [84, 30, 118], target: [0, 0, 0], fov: BASE_FOV };

/** The view from Earth toward (ra, dec): stand just behind Earth and look through it. */
function earthView(ra: number, dec: number, fov: number): Pose {
  const [x, y, z] = radecToVec(ra, dec);
  return { pos: [-x * MIN_DIST, -y * MIN_DIST, -z * MIN_DIST], target: [0, 0, 0], fov: Math.max(MIN_FOV, Math.min(BASE_FOV, fov)) };
}

/** Uniforms shared by the sky and the hosts so both light up for the same watches. */
function useWatchUniforms(watches: Watch[], draft: Draft | null) {
  const u = useMemo(
    () => ({
      uWatches: { value: Array.from({ length: MAX_SHADER_WATCHES }, () => new THREE.Vector4()) },
      uWatchCount: { value: 0 },
      uDraft: { value: new THREE.Vector4() },
      uDraftOn: { value: 0 },
      uDraftBlocked: { value: 0 },
    }),
    [],
  );
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const n = Math.min(watches.length, MAX_SHADER_WATCHES);
    for (let i = 0; i < n; i++) capUniform(watches[i].sphere, u.uWatches.value[i]);
    u.uWatchCount.value = n;
    u.uDraftOn.value = draft ? 1 : 0;
    if (draft) capUniform(draft.sphere, u.uDraft.value);
    u.uDraftBlocked.value = draft?.result.kind === "blocked" ? 1 : 0;
    invalidate();
  }, [watches, draft, u, invalidate]);
  return u;
}

type WatchUniforms = ReturnType<typeof useWatchUniforms>;

function SkyShell({
  data,
  layers,
  heatType,
  watchUniforms,
  baker,
  drift,
  onHeatMax,
}: {
  data: MapData;
  layers: Layers;
  heatType: CatchType | "all";
  watchUniforms: WatchUniforms;
  baker: SkyBaker;
  drift: boolean;
  onHeatMax: (max: number) => void;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const gl = useThree((s) => s.gl);
  const { texture, buf } = useMemo(() => {
    const buf = new Uint8Array(TEX_W * TEX_H * 4);
    bakeFootprint(buf, data.footprint);
    bakeTonight(buf, data.tonight);
    const texture = new THREE.DataTexture(buf, TEX_W, TEX_H, THREE.RGBAFormat);
    texture.wrapS = THREE.RepeatWrapping;
    texture.magFilter = THREE.LinearFilter;
    texture.minFilter = THREE.LinearFilter;
    texture.generateMipmaps = false;
    texture.needsUpdate = true;
    return { texture, buf };
  }, [data]);

  useEffect(() => {
    onHeatMax(bakeHeatmap(buf, data.heatmap, heatType));
    texture.needsUpdate = true;
    invalidate();
  }, [buf, texture, data.heatmap, heatType, onHeatMax, invalidate]);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: skyVertex,
        fragmentShader: skyFragment,
        side: THREE.BackSide,
        depthWrite: false,
        uniforms: {
          ...watchUniforms,
          uTex: { value: texture },
          uCubeBase: { value: baker.cubeBase.texture },
          uCubeGlow: { value: baker.cubeGlow.texture },
          uDetailBase: { value: baker.detailBase.texture },
          uDetailGlow: { value: baker.detailGlow.texture },
          uDetailVP: { value: baker.detailVP },
          uDetailOn: { value: 0 },
          uBaked: { value: 0 },
          uArt: { value: 1 },
          uTime: { value: 0 },
          uDrift: { value: 0 },
          uZone: { value: 1 },
          uGrounds: { value: 0 },
          uHeat: { value: 0 },
          uTonight: { value: 0 },
          cDeep: { value: tokenColor("--space", "#000000") },
          cGrid: { value: tokenColor("--grid", "#1f2127") },
          cRubin: { value: tokenColor("--rubin", "#6fd6c6") },
          cSolar: { value: tokenColor("--ground-ecliptic", "#d9be7c") },
          cBulge: { value: tokenColor("--ground-bulge", "#d98ba6") },
          cHigh: { value: tokenColor("--ground-high", "#b7a5f0") },
          cAccent: { value: tokenColor("--accent", "#a3b8ff") },
          cBlocked: { value: tokenColor("--supernova", "#e8836a") },
          cHeatHi: { value: tokenColor("--ink", "#f4f4f5") },
        },
      }),
    [texture, watchUniforms, baker],
  );


  useEffect(() => {
    material.uniforms.uZone.value = layers.zone ? 1 : 0;
    material.uniforms.uGrounds.value = layers.grounds ? 1 : 0;
    material.uniforms.uHeat.value = layers.heatmap ? 1 : 0;
    material.uniforms.uTonight.value = layers.tonight ? 1 : 0;
    material.uniforms.uArt.value = layers.art ? 1 : 0;
    material.uniforms.uDrift.value = drift ? 1 : 0;
    invalidate();
  }, [layers, drift, material, invalidate]);

  useFrame(({ clock }) => {
    // Bake the illustrated sky progressively, one cube face per frame, only once the layer is switched on.
    if (layers.art && material.uniforms.uBaked.value < 1) {
      if (baker.bakeStep(gl)) {
        material.uniforms.uBaked.value = 1;
        view.bakeInfo = { cubeMs: Math.round(baker.lastBakeMs), detailMs: 0, face: baker.quality.face };
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

const bubbleGeometry = new THREE.SphereGeometry(1, 40, 20);

function WatchBubble({ sphere, blocked, faint }: { sphere: Sphere; blocked?: boolean; faint?: boolean }) {
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: bubbleVertex,
        fragmentShader: bubbleFragment,
        transparent: true,
        depthWrite: false,
        uniforms: { uColor: { value: new THREE.Color() }, uOpacity: { value: 1 } },
      }),
    [],
  );
  useEffect(() => () => material.dispose(), [material]);
  material.uniforms.uColor.value.copy(tokenColor(blocked ? "--supernova" : "--accent", blocked ? "#e8836a" : "#a3b8ff"));
  material.uniforms.uOpacity.value = faint ? 0.6 : 1;
  const [x, y, z] = radecToVec(sphere.ra_deg, sphere.dec_deg);
  const r = WATCH_D * Math.sin((sphere.radius_deg * Math.PI) / 180);
  return (
    <mesh
      geometry={bubbleGeometry}
      material={material}
      position={[x * WATCH_D, y * WATCH_D, z * WATCH_D]}
      scale={r}
      renderOrder={4}
    />
  );
}

/** Fixed-pixel-size markers at every watch centre, so even a 3 arcminute watch stays findable. */
function WatchMarkers({ watches, draft }: { watches: Watch[]; draft: Draft | null }) {
  const dpr = useThree((s) => s.viewport.dpr);
  const geometry = useMemo(() => {
    const list = [
      ...watches.map((w) => ({ s: w.sphere, b: 0 })),
      ...(draft ? [{ s: draft.sphere, b: draft.result.kind === "blocked" ? 1 : 0 }] : []),
    ];
    const pos = new Float32Array(list.length * 3);
    const blocked = new Float32Array(list.length);
    list.forEach((e, i) => {
      const [x, y, z] = radecToVec(e.s.ra_deg, e.s.dec_deg);
      pos.set([x * WATCH_D, y * WATCH_D, z * WATCH_D], i * 3);
      blocked[i] = e.b;
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aBlocked", new THREE.BufferAttribute(blocked, 1));
    return g;
  }, [watches, draft]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: markerVertex,
        fragmentShader: markerFragment,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        uniforms: {
          uPx: { value: 1 },
          cAccent: { value: tokenColor("--accent", "#a3b8ff") },
          cBlocked: { value: tokenColor("--supernova", "#e8836a") },
        },
      }),
    [],
  );
  material.uniforms.uPx.value = dpr;
  return <points geometry={geometry} material={material} frustumCulled={false} renderOrder={5} />;
}


function hostPos(positionsRef: React.RefObject<Float32Array | null>, i: number): V3 | null {
  const p = positionsRef.current;
  return p ? [p[i * 3], p[i * 3 + 1], p[i * 3 + 2]] : null;
}

/**
 * Owns camera-controls and runs every camera change: fly-to flights, the eased field of view, the
 * close-up focus (enter, switch, leave), the adaptive near plane and hover/selection fades.
 */
function Director({
  rig,
  index,
  positionsRef,
  starUniforms,
}: {
  rig: Rig;
  index: HostIndex;
  positionsRef: React.RefObject<Float32Array | null>;
  starUniforms: StarUniforms;
}) {
  const { state } = useStore();
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const gl = useThree((s) => s.gl);
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
    c.setLookAt(...OVERVIEW.pos, ...OVERVIEW.target, false);
    return c;
  }, [camera, gl, rig.reduced]);

  useEffect(() => {
    rig.controls = controls;
    rig.camera = camera;
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

  useEffect(() => {
    controls.enabled = state.mode === "look";
  }, [controls, state.mode]);

  // Focus: fly into the selected host, between hosts, or back out when it is closed.
  const prevSel = useRef<number | null>(null);
  const stateRef = useRef<State>(state);
  useEffect(() => {
    stateRef.current = state;
  });
  const sel = state.selectedStar;
  const trueScale = state.trueScale;
  useEffect(() => {
    const prev = prevSel.current;
    prevSel.current = sel;
    if (!rig.controls || !rig.camera) return;
    const s = stateRef.current;
    if (sel !== null) {
      const p = hostPos(positionsRef, sel);
      if (!p) return;
      if (prev === null) rig.saved = rig.flight?.kind === "back" ? rig.flight.to : currentPose(rig);
      const R = displayRadius(index.hosts.rad?.[sel] ?? 0);
      // Arrive from the side the camera is already on, a few stellar radii out.
      const cam = rig.camera.position;
      const dir = new THREE.Vector3(cam.x - p[0], cam.y - p[1], cam.z - p[2]);
      if (dir.lengthSq() < 1e-20) dir.set(0, 0, 1);
      // On a portrait screen the width is the tighter field, so stand further back to keep the whole disc in view.
      dir.normalize().multiplyScalar(R * 3.6 * Math.max(1, 0.85 / rig.camera.aspect));
      rig.limits = { min: R * 1.25, max: s.trueScale ? 700 : 320 };
      flyTo(rig, { pos: [p[0] + dir.x, p[1] + dir.y, p[2] + dir.z], target: p, fov: BASE_FOV }, "focus");
      rig.selectedT = 0;
      starUniforms.uSelected.value = sel;
    } else if (prev !== null) {
      rig.limits = { min: 0.3, max: s.trueScale ? 700 : 320 };
      starUniforms.uSelected.value = -1;
      if (rig.flight?.kind === "jump") return;
      const d = s.draft;
      const to = d ? earthView(d.sphere.ra_deg, d.sphere.dec_deg, Math.max(3, d.sphere.radius_deg * 12)) : (rig.saved ?? OVERVIEW);
      rig.saved = null;
      flyTo(rig, to, "back");
    }
    invalidate();
  }, [sel, trueScale, rig, index, positionsRef, starUniforms, invalidate]);

  useEffect(() => {
    if (sel === null) rig.limits = { min: 0.3, max: trueScale ? 700 : 320 };
    if (!rig.flight && rig.controls) applyLimits(rig);
  }, [trueScale, sel, rig]);

  const focusPos = useMemo(() => new THREE.Vector3(), []);
  let lastFov = -1;
  useFrame((_, dt) => {
    const step = Math.min(dt, 0.1);
    if (!rig.reduced) rig.time += step;
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

    // Near plane follows the focused star, so a 0.1 R☉ dwarf a few radii away is never clipped.
    const p = sel !== null ? hostPos(positionsRef, sel) : null;
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

    if (hud.fov && camera.fov !== lastFov) {
      lastFov = camera.fov;
      hud.fov.textContent = `${camera.fov < 10 ? camera.fov.toFixed(1) : Math.round(camera.fov)}°`;
    }
    if (busy) invalidate();
  }, -1);

  return null;
}

/**
 * All pointer input on the canvas: draw a watch (draw mode), hover and pick a star (look mode),
 * pinch and wheel zoom (both modes), and the pointer's RA/Dec for the status bar.
 */
function Input({
  data,
  index,
  positionsRef,
  rig,
  baker,
}: {
  data: MapData;
  index: HostIndex;
  positionsRef: React.RefObject<Float32Array | null>;
  rig: Rig;
  baker: SkyBaker;
}) {
  const { state, dispatch } = useStore();
  const gl = useThree((s) => s.gl);
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const size = useThree((s) => s.size);
  const invalidate = useThree((s) => s.invalidate);
  const modeRef = useRef(state.mode);
  const artRef = useRef(state.layers.art);
  const sizeRef = useRef(size);
  const selRef = useRef(state.selectedStar);
  useEffect(() => {
    modeRef.current = state.mode;
    artRef.current = state.layers.art;
    sizeRef.current = size;
    selRef.current = state.selectedStar;
  }, [state.mode, state.layers.art, size, state.selectedStar]);

  useEffect(() => {
    const el = gl.domElement;
    const raycaster = new THREE.Raycaster();
    const pointers = new Map<number, { x: number; y: number }>();
    let drag: { id: number; center: Vec3; x: number; y: number; moved: boolean } | null = null;
    let tap: { x: number; y: number } | null = null;
    let pinch = 0;
    let raf = 0;
    let hoverRaf = 0;
    let pending: Sphere | null = null;
    let detailTimer = 0;

    const scheduleDetail = () => {
      clearTimeout(detailTimer);
      detailTimer = window.setTimeout(() => {
        if (camera.fov < 25 && artRef.current) {
          baker.bakeDetail(gl, camera, sizeRef.current.width, sizeRef.current.height);
          if (view.bakeInfo) view.bakeInfo.detailMs = Math.round(baker.lastDetailMs);
        } else {
          baker.detailOn = false;
        }
        invalidate();
      }, 260);
    };

    const zoomBy = (f: number) => {
      const c = rig.controls;
      if (!c) return;
      interrupt(rig);
      const smooth = !rig.reduced;
      const dist = c.getSpherical(new THREE.Spherical(), true).radius;
      if (selRef.current !== null) {
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
      scheduleDetail();
    };

    view.jumpTo = (ra, dec, fovDeg) => {
      flyTo(rig, earthView(ra, dec, fovDeg), "jump");
      if (selRef.current !== null) dispatch({ type: "selectStar", index: null });
      invalidate();
      scheduleDetail();
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

    const sphereFrom = (center: Vec3, radius: number): Sphere => {
      const { ra, dec } = vecToRadec(center);
      const r = Math.min(SPHERE_RADIUS_MAX, Math.max(SPHERE_RADIUS_MIN, radius));
      return { ra_deg: Number(ra.toFixed(5)), dec_deg: Number(dec.toFixed(5)), radius_deg: Number(r.toFixed(r < 1 ? 3 : 2)) };
    };

    const flush = (dragging: boolean) => {
      raf = 0;
      if (!pending) return;
      dispatch({ type: "draft", draft: { sphere: pending, result: classify(pending, index, data.footprint), dragging } });
    };

    /** Nearest host to a screen point within `maxPx`, or -1. */
    const nearestHost = (clientX: number, clientY: number, maxPx: number) => {
      const pos = positionsRef.current;
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

    const setHover = (i: number) => {
      if (i === rig.hover) return;
      if (i >= 0 && rig.hover >= 0) rig.hoverT = 0; // a new star: the ring starts fresh
      rig.hover = i;
      el.style.cursor = i >= 0 ? "pointer" : "";
      if (hud.hover && i >= 0) hud.hover.textContent = index.hosts.name[i];
      invalidate();
    };

    const down = (e: PointerEvent) => {
      interrupt(rig);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        // Second finger: pinch zoom. Drop any half-drawn watch.
        const [a, b] = [...pointers.values()];
        pinch = Math.hypot(a.x - b.x, a.y - b.y);
        if (drag) {
          drag = null;
          dispatch({ type: "draft", draft: null });
        }
        tap = null;
        return;
      }
      if (pointers.size > 2 || e.button !== 0) return;
      if (modeRef.current === "draw") {
        drag = { id: e.pointerId, center: skyDir(e.clientX, e.clientY), x: e.clientX, y: e.clientY, moved: false };
        el.setPointerCapture(e.pointerId);
      } else {
        tap = { x: e.clientX, y: e.clientY };
      }
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
      if (e.pointerType === "mouse") {
        if (hud.pointer) {
          const { ra, dec } = vecToRadec(skyDir(e.clientX, e.clientY));
          hud.pointer.textContent = `${formatRa(ra)}  ${formatDec(dec)}`;
        }
        if (modeRef.current === "look" && e.buttons === 0 && !hoverRaf) {
          const x = e.clientX;
          const y = e.clientY;
          hoverRaf = requestAnimationFrame(() => {
            hoverRaf = 0;
            setHover(nearestHost(x, y, 14));
          });
        }
      }
      if (!drag || e.pointerId !== drag.id) return;
      if (!drag.moved && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 6) return;
      drag.moved = true;
      pending = sphereFrom(drag.center, separationDeg(drag.center, skyDir(e.clientX, e.clientY)));
      if (!raf) raf = requestAnimationFrame(() => flush(true));
    };

    const up = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = 0;
      if (drag && e.pointerId === drag.id) {
        // A tap without a drag places a 1 degree watch, which the inspector's slider can resize.
        pending = drag.moved ? sphereFrom(drag.center, separationDeg(drag.center, skyDir(e.clientX, e.clientY))) : sphereFrom(drag.center, 1);
        cancelAnimationFrame(raf);
        flush(false);
        drag = null;
        return;
      }
      if (tap && Math.hypot(e.clientX - tap.x, e.clientY - tap.y) < 6) {
        // Picking a host flies to it. A tap on empty sky does nothing, so a stray tap never ends a close-up.
        const i = nearestHost(e.clientX, e.clientY, e.pointerType === "mouse" ? 14 : 22);
        if (i >= 0 && i !== selRef.current) dispatch({ type: "selectStar", index: i });
      }
      tap = null;
    };

    const cancel = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = 0;
      if (drag && e.pointerId === drag.id) {
        drag = null;
        dispatch({ type: "draft", draft: null });
      }
    };

    const leave = () => setHover(-1);

    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomBy(Math.exp(Math.max(-60, Math.min(60, e.deltaY)) * 0.004));
    };

    const onRest = () => scheduleDetail();
    const ctl = rig.controls;
    ctl?.addEventListener("rest", onRest);

    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", cancel);
    el.addEventListener("pointerleave", leave);
    el.addEventListener("wheel", wheel, { passive: false });
    return () => {
      cancelAnimationFrame(raf);
      cancelAnimationFrame(hoverRaf);
      clearTimeout(detailTimer);
      view.jumpTo = null;
      ctl?.removeEventListener("rest", onRest);
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", cancel);
      el.removeEventListener("pointerleave", leave);
      el.removeEventListener("wheel", wheel);
    };
  }, [gl, camera, dispatch, index, data.footprint, positionsRef, rig, baker, invalidate]);

  // Draw mode never hovers.
  useEffect(() => {
    if (state.mode === "draw" && rig.hover >= 0) {
      rig.hover = -1;
      gl.domElement.style.cursor = "";
    }
  }, [state.mode, rig, gl]);

  // Re-bake the zoomed detail patch when the illustrated layer is switched back on.
  useEffect(() => {
    if (state.layers.art && camera.fov < 25) {
      baker.bakeDetail(gl, camera, size.width, size.height);
      invalidate();
    }
  }, [state.layers.art, baker, gl, camera, size.width, size.height, invalidate]);

  return null;
}

/** Keeps the hovered host's name label beside it. */
function HoverAnchor({ rig, positionsRef }: { rig: Rig; positionsRef: React.RefObject<Float32Array | null> }) {
  const v = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ camera, size }) => {
    const el = hud.hover;
    if (!el) return;
    const p = rig.hover >= 0 ? hostPos(positionsRef, rig.hover) : null;
    if (!p) {
      el.dataset.visible = "false";
      return;
    }
    v.set(...p).project(camera);
    const x = ((v.x + 1) / 2) * size.width;
    const y = ((1 - v.y) / 2) * size.height;
    el.style.transform = `translate(${(x + 14).toFixed(1)}px, ${(y - 10).toFixed(1)}px)`;
    el.dataset.visible = v.z < 1 ? "true" : "false";
  });
  return null;
}

/** Keeps the floating readout next to the watch being drawn. */
function ReadoutAnchor() {
  const v = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ camera, size }) => {
    const el = hud.readout;
    if (!el) return;
    if (!hud.readoutTarget) {
      el.dataset.visible = "false";
      return;
    }
    v.copy(hud.readoutTarget).project(camera);
    const visible = v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05;
    const x = ((v.x + 1) / 2) * size.width;
    const y = ((1 - v.y) / 2) * size.height;
    const cam = camera as THREE.PerspectiveCamera;
    const dist = cam.position.distanceTo(hud.readoutTarget);
    const rpx = Math.min((hud.readoutRadius / dist) * (size.height / 2 / Math.tan((cam.fov * Math.PI) / 360)), size.width);
    const w = el.offsetWidth;
    let left = x + rpx + 14;
    if (left + w > size.width - 8) left = x - rpx - 14 - w;
    left = Math.max(8, Math.min(left, size.width - w - 8));
    const top = Math.max(56, Math.min(y - el.offsetHeight / 2, size.height - el.offsetHeight - 8));
    el.style.transform = `translate(${left.toFixed(1)}px, ${top.toFixed(1)}px)`;
    el.dataset.visible = visible ? "true" : "false";
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

function Invalidator({ deps }: { deps: unknown[] }) {
  const invalidate = useThree((s) => s.invalidate);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => invalidate(), deps);
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

export default function Scene({ data, index, showFps, onHeatMax }: SceneProps) {
  const { state } = useStore();
  const positionsRef = useRef<Float32Array | null>(null);
  const phone = useMemo(() => isPhone(), []);
  const reduced = useMemo(() => reducedMotion(), []);
  const rig = useMemo(() => createRig(reduced, BASE_FOV), [reduced]);
  const baker = useMemo(() => new SkyBaker(data.sky, phone ? QUALITY_PHONE : QUALITY_DESKTOP), [data.sky, phone]);
  useEffect(() => () => baker.dispose(), [baker]);
  // The nebula layer drifts only on desktop, with motion allowed and the layer on.
  const drift = !phone && !reduced && state.layers.art;
  // The focused star's surface is alive unless motion is reduced; then it is a still image.
  const living = state.selectedStar !== null && !reduced;

  useEffect(() => {
    if (state.draft) {
      const s = state.draft.sphere;
      const [x, y, z] = radecToVec(s.ra_deg, s.dec_deg);
      hud.readoutTarget = new THREE.Vector3(x * WATCH_D, y * WATCH_D, z * WATCH_D);
      hud.readoutRadius = WATCH_D * Math.sin((s.radius_deg * Math.PI) / 180);
    } else {
      hud.readoutTarget = null;
    }
  }, [state.draft]);

  return (
    <Canvas
      dpr={[1, 2]}
      frameloop="demand"
      camera={{ fov: BASE_FOV, near: 0.05, far: 5000, position: OVERVIEW.pos }}
      gl={{ antialias: false, powerPreference: "high-performance" }}
      onCreated={({ gl }) => gl.setClearColor(tokenColor("--space", "#000000"))}
      aria-hidden="true"
    >
      <Loop want={showFps || drift || living ? "always" : "demand"} />
      <SceneContent data={data} index={index} onHeatMax={onHeatMax} positionsRef={positionsRef} baker={baker} drift={drift} rig={rig} phone={phone} />
      <EffectComposer multisampling={phone ? 0 : 4}>
        <Bloom mipmapBlur luminanceThreshold={0.85} luminanceSmoothing={0.25} intensity={0.9} radius={0.7} resolutionScale={phone ? 0.5 : 1} />
      </EffectComposer>
      {showFps && <FpsMeter />}
    </Canvas>
  );
}

function SceneContent({
  data,
  index,
  onHeatMax,
  positionsRef,
  baker,
  drift,
  rig,
  phone,
}: {
  data: MapData;
  index: HostIndex;
  onHeatMax: (max: number) => void;
  positionsRef: React.RefObject<Float32Array | null>;
  baker: SkyBaker;
  drift: boolean;
  rig: Rig;
  phone: boolean;
}) {
  const { state } = useStore();
  const watchUniforms = useWatchUniforms(state.watches, state.draft);
  const starUniforms = useMemo(() => createStarUniforms(), []);
  const draft = state.draft;

  return (
    <>
      <Director rig={rig} index={index} positionsRef={positionsRef} starUniforms={starUniforms} />
      <SkyShell
        data={data}
        layers={state.layers}
        heatType={state.heatType}
        watchUniforms={watchUniforms}
        baker={baker}
        drift={drift}
        onHeatMax={onHeatMax}
      />
      <CatalogStars data={data} visible={state.layers.stars} watchUniforms={watchUniforms} />
      <Hosts index={index} trueScale={state.trueScale} watchUniforms={watchUniforms} starUniforms={starUniforms} positionsRef={positionsRef} />
      <CloseUp index={index} selected={state.selectedStar} positionsRef={positionsRef} starUniforms={starUniforms} rig={rig} octaves={phone ? 2 : 4} />
      <Earth />
      {state.watches.map((w) => (
        <WatchBubble key={w.id} sphere={w.sphere} faint />
      ))}
      {draft && <WatchBubble sphere={draft.sphere} blocked={draft.result.kind === "blocked"} />}
      <WatchMarkers watches={state.watches} draft={draft} />
      <Input data={data} index={index} positionsRef={positionsRef} rig={rig} baker={baker} />
      <ReadoutAnchor />
      <HoverAnchor rig={rig} positionsRef={positionsRef} />
      <Invalidator deps={[state.draft, state.selectedStar, state.watches, state.mode, state.layers.stars]} />
    </>
  );
}
