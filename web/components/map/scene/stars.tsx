"use client";

// Stars: catalogue stars on the sky shell and planet hosts in 3D, both as additive point sprites
// (one draw call each), plus the close-up of the focused host (surface sphere + corona).

import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import type { MapData } from "@/lib/data";
import type { HostIndex } from "@/lib/classify";
import { radecToVec } from "@/lib/sky";
import { bvToTeff } from "@/lib/starColor";
import { BASE_FOV, displayRadius, linearStarColor, sceneDistance, STAR_R, tokenColor } from "./constants";
import { coronaFragment, coronaVertex, spriteFragment, spriteVertex, surfaceFragment, surfaceVertex } from "./starShaders";
import type { Rig } from "./rig";

/** Uniforms the scene animates for hover, selection and the sprite-to-sphere swap. */
export function createStarUniforms() {
  return {
    uHover: { value: -1 },
    uHoverT: { value: 0 },
    uSelected: { value: -1 },
    uSelectedT: { value: 0 },
    uFocusFade: { value: 0 },
  };
}
export type StarUniforms = ReturnType<typeof createStarUniforms>;

type WatchUniformSet = Record<string, { value: unknown }>;

function spriteMaterial(uniforms: Record<string, { value: unknown }>) {
  return new THREE.ShaderMaterial({
    vertexShader: spriteVertex,
    fragmentShader: spriteFragment,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uPx: { value: 1 },
      uFovScale: { value: 1 },
      cAccent: { value: tokenColor("--accent", "#a3b8ff") },
      ...uniforms,
    },
  });
}

function useSpriteFrame(material: THREE.ShaderMaterial) {
  const dpr = useThree((s) => s.viewport.dpr);
  useFrame(({ camera }) => {
    material.uniforms.uPx.value = dpr;
    // Stars grow a little as the field narrows, like a telescope gathering more light.
    material.uniforms.uFovScale.value = Math.min(2.2, Math.sqrt(BASE_FOV / (camera as THREE.PerspectiveCamera).fov));
  });
}

/** Bright catalogue stars (Yale BSC) on the sky shell. Colour from B-V via Teff. */
export function CatalogStars({ data, visible, watchUniforms }: { data: MapData; visible: boolean; watchUniforms: WatchUniformSet }) {
  const geometry = useMemo(() => {
    const st = data.sky.stars;
    const n = st.ra.length;
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    const mag = new Float32Array(n);
    const idx = new Float32Array(n).fill(-10);
    for (let i = 0; i < n; i++) {
      const [x, y, z] = radecToVec(st.ra[i], st.dec[i]);
      pos.set([x * STAR_R, y * STAR_R, z * STAR_R], i * 3);
      col.set(linearStarColor(Number.isFinite(st.bv[i]) ? bvToTeff(st.bv[i]) : 0), i * 3);
      mag[i] = st.mag[i];
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aColor", new THREE.BufferAttribute(col, 3));
    g.setAttribute("aMag", new THREE.BufferAttribute(mag, 1));
    g.setAttribute("aIndex", new THREE.BufferAttribute(idx, 1));
    return g;
  }, [data.sky.stars]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const material = useMemo(
    () =>
      spriteMaterial({
        ...watchUniforms,
        ...createStarUniforms(),
        uMinI: { value: 0.05 },
        uProximity: { value: 0 },
        uRings: { value: 0 },
      }),
    [watchUniforms],
  );
  useSpriteFrame(material);
  return <points geometry={geometry} material={material} frustumCulled={false} visible={visible} renderOrder={0} />;
}

/** Planet hosts at their 3D positions. Colour from TIC Teff, size from V magnitude, brighter up close. */
export function Hosts({
  index,
  trueScale,
  watchUniforms,
  starUniforms,
  positionsRef,
}: {
  index: HostIndex;
  trueScale: boolean;
  watchUniforms: WatchUniformSet;
  starUniforms: StarUniforms;
  positionsRef: React.RefObject<Float32Array | null>;
}) {
  const geometry = useMemo(() => {
    const { hosts } = index;
    const n = hosts.count;
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    const mag = new Float32Array(n);
    const idx = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const r = sceneDistance(hosts.dist[i], trueScale);
      const d = index.dirs[i];
      pos.set([d[0] * r, d[1] * r, d[2] * r], i * 3);
      col.set(linearStarColor(hosts.teff[i]), i * 3);
      // No V magnitude listed (a handful of faint hosts): treat as 12th magnitude.
      mag[i] = hosts.vmag?.[i] != null && hosts.vmag[i] < 99 ? hosts.vmag[i] : 12;
      idx[i] = i;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aColor", new THREE.BufferAttribute(col, 3));
    g.setAttribute("aMag", new THREE.BufferAttribute(mag, 1));
    g.setAttribute("aIndex", new THREE.BufferAttribute(idx, 1));
    g.computeBoundingSphere();
    return g;
  }, [index, trueScale]);

  useEffect(() => {
    positionsRef.current = geometry.getAttribute("position").array as Float32Array;
    return () => geometry.dispose();
  }, [geometry, positionsRef]);

  const material = useMemo(
    () => spriteMaterial({ ...watchUniforms, ...starUniforms, uMinI: { value: 0.3 }, uProximity: { value: 1 }, uRings: { value: 1 } }),
    [watchUniforms, starUniforms],
  );
  useSpriteFrame(material);
  return <points geometry={geometry} material={material} frustumCulled={false} renderOrder={2} />;
}

const sphereGeometry = new THREE.SphereGeometry(1, 128, 64);
const quadGeometry = new THREE.PlaneGeometry(2, 2);
const CORONA_EXTENT = 4;

/**
 * The focused host up close: an animated surface sphere at the star's real radius (scaled for the
 * view) and a corona billboard. Fades in as the star grows past a few pixels; the sprite fades out.
 */
export function CloseUp({
  index,
  selected,
  positionsRef,
  starUniforms,
  rig,
  octaves,
}: {
  index: HostIndex;
  selected: number | null;
  positionsRef: React.RefObject<Float32Array | null>;
  starUniforms: StarUniforms;
  rig: Rig;
  octaves: number;
}) {
  const group = useRef<THREE.Group>(null);
  const corona = useRef<THREE.Mesh>(null);
  const surface = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: surfaceVertex,
        fragmentShader: surfaceFragment(octaves),
        transparent: true,
        uniforms: {
          uColor: { value: new THREE.Vector3(1, 1, 1) },
          uLimbColor: { value: new THREE.Vector3(1, 1, 1) },
          uHot: { value: 0.5 },
          uLimb: { value: 0.6 },
          uTime: { value: 0 },
          uSeed: { value: 0 },
          uOpacity: { value: 0 },
        },
      }),
    [octaves],
  );
  const coronaMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: coronaVertex,
        fragmentShader: coronaFragment,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        uniforms: {
          uColor: { value: new THREE.Vector3(1, 1, 1) },
          uExtent: { value: CORONA_EXTENT },
          uTime: { value: 0 },
          uSeed: { value: 0 },
          uOpacity: { value: 0 },
        },
      }),
    [],
  );
  useEffect(
    () => () => {
      surface.dispose();
      coronaMat.dispose();
    },
    [surface, coronaMat],
  );

  const radius = selected === null ? 0 : displayRadius(index.hosts.rad?.[selected] ?? 0);

  useEffect(() => {
    if (selected === null) return;
    const teff = index.hosts.teff[selected];
    const c = linearStarColor(teff);
    // The limb is cooler: take the colour of a star about 15% cooler (white stays white when Teff is missing).
    const l = linearStarColor(teff > 0 ? teff * 0.85 : 0);
    const hot = teff > 0 ? THREE.MathUtils.clamp((teff - 2500) / 9500, 0, 1) : 0.4;
    const seed = ((index.hosts.tic[selected] % 997) / 997) * 50;
    surface.uniforms.uColor.value.set(...c);
    surface.uniforms.uLimbColor.value.set(...l);
    surface.uniforms.uHot.value = hot;
    // Linear limb darkening coefficient in the visible: strong for cool dwarfs, weaker for hot stars.
    surface.uniforms.uLimb.value = THREE.MathUtils.lerp(0.82, 0.4, hot);
    surface.uniforms.uSeed.value = seed;
    // The corona leans a little whiter than the photosphere.
    coronaMat.uniforms.uColor.value.set(c[0] * 0.8 + 0.2, c[1] * 0.8 + 0.2, c[2] * 0.8 + 0.2);
    coronaMat.uniforms.uSeed.value = seed;
  }, [selected, index, surface, coronaMat]);

  const tmp = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ camera, size }) => {
    const g = group.current;
    const pos = positionsRef.current;
    if (!g) return;
    if (selected === null || !pos) {
      g.visible = false;
      starUniforms.uFocusFade.value = 0;
      return;
    }
    tmp.set(pos[selected * 3], pos[selected * 3 + 1], pos[selected * 3 + 2]);
    g.position.copy(tmp);
    g.scale.setScalar(radius);
    const cam = camera as THREE.PerspectiveCamera;
    const dist = cam.position.distanceTo(tmp);
    // Projected radius in CSS pixels: the sprite hands over to the sphere between 2 and 6 px.
    const px = (radius / Math.max(dist, 1e-9)) * (size.height / 2 / Math.tan((cam.fov * Math.PI) / 360));
    const fade = THREE.MathUtils.smoothstep(px, 2, 6);
    starUniforms.uFocusFade.value = fade;
    g.visible = fade > 0.004;
    surface.uniforms.uOpacity.value = fade;
    coronaMat.uniforms.uOpacity.value = fade;
    surface.uniforms.uTime.value = rig.time;
    coronaMat.uniforms.uTime.value = rig.time;
    corona.current?.quaternion.copy(cam.quaternion);
  });

  return (
    <group ref={group} visible={false}>
      <mesh geometry={sphereGeometry} material={surface} renderOrder={1} />
      <mesh ref={corona} geometry={quadGeometry} material={coronaMat} scale={CORONA_EXTENT} renderOrder={3} />
    </group>
  );
}
