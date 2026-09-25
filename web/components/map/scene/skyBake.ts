// The illustrated sky: Milky Way, dust lanes, Magellanic Clouds, faint background stars and nebulae.
//
// Noise is expensive, so none of it runs per frame. It is baked once at load into two cubemaps:
//   base: background stars + Milky Way + dust + dark nebulae
//   glow: emission, reflection and supernova-remnant nebulae (kept separate so it can drift gently)
// When the user zooms in (narrow field of view), a screen-sized "detail" patch is re-baked for the
// current view at higher resolution and more octaves, so zoomed nebulae stay sharp.
//
// Positions and sizes are real (see public/data/sky-objects.json and CREDITS.md). Shapes are illustrations.

import * as THREE from "three";
import { radecToVec } from "@/lib/sky";
import { noiseGlsl } from "./noise";

export type SkyObjects = {
  nebulae: [number, number, number, number, number][];
  stars: { ra: number[]; dec: number[]; mag: number[]; bv: number[] };
  sources: { nebulae: string; stars: string };
};

export type BakeQuality = { face: number; octaves: number; detailOctaves: number; detailMax: number };

export const QUALITY_DESKTOP: BakeQuality = { face: 1024, octaves: 5, detailOctaves: 6, detailMax: 2048 };
export const QUALITY_PHONE: BakeQuality = { face: 512, octaves: 3, detailOctaves: 4, detailMax: 1024 };

const GALACTIC = /* glsl */ `
  const float DEG = 0.01745329252;
  // Equatorial scene direction -> galactic (l, b) in radians, l in (-pi, pi].
  vec2 galactic(vec3 d) {
    vec3 a = vec3(d.x, -d.z, d.y);
    vec3 g = a * mat3(
      -0.0548755604, -0.8734370902, -0.4838350155,
       0.4941094279, -0.44482963,    0.7469822445,
      -0.867666149,  -0.1980763734,  0.4559837762
    );
    return vec2(atan(g.y, g.x), asin(clamp(g.z, -1.0, 1.0)));
  }
  float angle(vec3 a, vec3 b) { return 2.0 * asin(clamp(length(a - b) * 0.5, 0.0, 1.0)); }
  float hash13(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.zyx + 31.32);
    return fract((p.x + p.y) * p.z);
  }
  vec3 hash33(vec3 p) {
    p = fract(p * vec3(0.1031, 0.1030, 0.0973));
    p += dot(p, p.yxz + 33.33);
    return fract((p.xxy + p.yxx) * p.zyx);
  }
`;

const milkyWayFragment = /* glsl */ `
  precision highp float;
  ${noiseGlsl}
  ${GALACTIC}
  uniform vec3 uLmc;
  uniform vec3 uSmc;
  varying vec3 vDir;

  void main() {
    vec3 d = normalize(vDir);
    vec2 lb = galactic(d);
    float l = lb.x;
    float b = lb.y;
    float lDeg = l / DEG;
    float bDeg = b / DEG;

    // Band: thicker and brighter toward the galactic centre in Sagittarius.
    float core = exp(-pow(l / 0.75, 2.0));
    float sigma = (3.2 + 6.5 * exp(-pow(l / 0.45, 2.0))) * DEG;
    float band = (0.2 + 0.8 * core) * exp(-pow(b / sigma, 2.0));
    band += 0.55 * exp(-pow(l / 0.28, 2.0) - pow(b / 0.15, 2.0)); // the bulge
    if (band > 0.002) band *= 0.5 + 0.9 * fbm(d * 7.0);          // star clouds

    // Dust: a general wispy layer plus the Great Rift (Cygnus to Sagittarius, slightly north of the plane).
    float rift = smoothstep(-10.0, 0.0, lDeg) * (1.0 - smoothstep(70.0, 88.0, lDeg));
    float laneCentre = 1.2 * rift;
    float laneWidth = 2.2 + 2.2 * rift;
    float lane = exp(-pow((bDeg - laneCentre) / laneWidth, 2.0));
    // Dust noise is only evaluated near the plane, where it can show.
    float dust = 0.0;
    if (abs(bDeg) < 25.0) {
      float dn = warped(d * 13.0, 1.7);
      dust = lane * smoothstep(0.4, 0.7, dn) * (0.45 + 0.55 * rift);
      dust += exp(-pow(bDeg / 7.0, 2.0)) * smoothstep(0.55, 0.8, warped(d * 24.0 + 3.0, 1.2)) * 0.45;
    }
    band *= 1.0 - clamp(dust, 0.0, 0.93);

    // Magellanic Clouds (noise only evaluated near them).
    float aL = angle(d, uLmc);
    float aS = angle(d, uSmc);
    float lmc = aL < 12.0 * DEG ? exp(-pow(aL / (3.3 * DEG), 2.0)) * (0.55 + 0.7 * fbm(d * 30.0)) : 0.0;
    float smc = aS < 6.0 * DEG ? exp(-pow(aS / (1.5 * DEG), 2.0)) * (0.55 + 0.7 * fbm(d * 45.0 + 7.0)) : 0.0;

    vec3 warm = vec3(0.78, 0.7, 0.6);
    vec3 cool = vec3(0.62, 0.64, 0.7);
    vec3 col = mix(cool, warm, core) * band * 0.2;
    col += vec3(0.7, 0.68, 0.72) * (lmc * 0.2 + smc * 0.14);

    // Faint background stars: one jittered candidate per cell, denser in the band.
    float px = max(length(fwidth(d)), 1e-5);
    vec3 cellP = d * 260.0;
    vec3 cell = floor(cellP);
    float h = hash13(cell);
    float density = 0.02 + 0.08 * clamp(band * 3.0, 0.0, 1.0);
    if (h < density) {
      vec3 star = normalize((cell + hash33(cell)) / 260.0);
      float size = max(px * 0.9, 0.00018);
      float s = exp(-pow(length(d - star) / size, 2.0));
      float mag = pow(hash13(cell + 11.0), 6.0);
      col += vec3(0.55, 0.57, 0.62) * s * (0.12 + 0.5 * mag);
    }

    gl_FragColor = vec4(col, 1.0);
  }
`;

const skyVertex = /* glsl */ `
  varying vec3 vDir;
  void main() {
    vDir = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const nebulaVertex = /* glsl */ `
  attribute vec3 aCenter;
  attribute float aRadius;
  attribute float aType;
  attribute float aBright;
  attribute float aSeed;
  varying vec2 vLocal;
  varying float vType;
  varying float vBright;
  varying float vSeed;
  const float EXTENT = 1.7;
  void main() {
    vec3 c = aCenter;
    vec3 up = abs(c.y) < 0.99 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
    vec3 t1 = normalize(cross(up, c));
    vec3 t2 = cross(c, t1);
    float half_ = tan(min(aRadius * EXTENT, 1.3));
    vec3 p = (c + (t1 * position.x + t2 * position.y) * half_) * 9.0;
    vLocal = position.xy * EXTENT;
    vType = aType;
    vBright = aBright;
    vSeed = aSeed;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const nebulaFragment = /* glsl */ `
  precision highp float;
  ${noiseGlsl}
  varying vec2 vLocal;
  varying float vType;
  varying float vBright;
  varying float vSeed;

  void main() {
    float r = length(vLocal);
    if (r > 1.7) discard;
    vec3 p = vec3(vLocal * 1.5, vSeed * 13.7);
    float n = warped(p, 1.5);
    float edge = smoothstep(1.65, 0.15, r + (n - 0.5) * 1.1);
    float core = exp(-r * r * 1.6);

    #ifdef DARK
      float a = edge * (0.45 + 0.55 * n) * vBright;
      gl_FragColor = vec4(0.0, 0.0, 0.0, clamp(a, 0.0, 0.95));
    #else
      vec3 col;
      float a;
      if (vType < 0.5) {
        // Emission (H-alpha): red to pink toward the bright core.
        a = edge * (0.3 + 0.7 * n) * (0.55 + 0.45 * core);
        col = mix(vec3(0.6, 0.16, 0.26), vec3(0.95, 0.5, 0.58), clamp(n * core * 1.4, 0.0, 1.0));
      } else if (vType < 1.5) {
        // Reflection: starlight scattered by dust, blue.
        a = edge * (0.25 + 0.6 * n) * (0.5 + 0.5 * core);
        col = mix(vec3(0.2, 0.3, 0.62), vec3(0.5, 0.64, 0.95), n * core);
      } else {
        // Supernova remnant: thin filaments on a shell, teal and red.
        float ridge = pow(1.0 - abs(2.0 * fbm(p * 2.2) - 1.0), 7.0);
        float shell = exp(-pow((r - 0.9 + (n - 0.5) * 0.5) / 0.22, 2.0));
        a = ridge * shell * 1.4;
        col = mix(vec3(0.3, 0.75, 0.72), vec3(0.85, 0.33, 0.35), smoothstep(0.35, 0.65, n));
      }
      gl_FragColor = vec4(col * a * vBright * 0.55, 1.0);
    #endif
  }
`;

function nebulaMesh(objects: SkyObjects, dark: boolean, uOctaves: { value: number }): THREE.Mesh {
  const list = objects.nebulae.filter((n) => (n[3] === 2) === dark);
  const base = new THREE.PlaneGeometry(2, 2);
  const g = new THREE.InstancedBufferGeometry();
  g.index = base.index;
  g.setAttribute("position", base.getAttribute("position"));
  const center = new Float32Array(list.length * 3);
  const radius = new Float32Array(list.length);
  const type = new Float32Array(list.length);
  const bright = new Float32Array(list.length);
  const seed = new Float32Array(list.length);
  list.forEach(([ra, dec, r, t, b], i) => {
    center.set(radecToVec(ra, dec), i * 3);
    radius[i] = (r * Math.PI) / 180;
    type[i] = t === 3 ? 2 : t; // shader: 0 emission, 1 reflection, 2 SNR
    bright[i] = b;
    seed[i] = (i * 0.618034) % 1;
  });
  g.setAttribute("aCenter", new THREE.InstancedBufferAttribute(center, 3));
  g.setAttribute("aRadius", new THREE.InstancedBufferAttribute(radius, 1));
  g.setAttribute("aType", new THREE.InstancedBufferAttribute(type, 1));
  g.setAttribute("aBright", new THREE.InstancedBufferAttribute(bright, 1));
  g.setAttribute("aSeed", new THREE.InstancedBufferAttribute(seed, 1));
  g.instanceCount = list.length;
  const m = new THREE.ShaderMaterial({
    vertexShader: nebulaVertex,
    fragmentShader: nebulaFragment,
    defines: dark ? { DARK: "" } : {},
    uniforms: { uOctaves },
    transparent: true,
    depthTest: false,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: dark ? THREE.NormalBlending : THREE.AdditiveBlending,
  });
  const mesh = new THREE.Mesh(g, m);
  mesh.frustumCulled = false;
  mesh.renderOrder = 1;
  return mesh;
}

export class SkyBaker {
  readonly cubeBase: THREE.WebGLCubeRenderTarget;
  readonly cubeGlow: THREE.WebGLCubeRenderTarget;
  detailBase: THREE.WebGLRenderTarget;
  detailGlow: THREE.WebGLRenderTarget;
  readonly detailVP = new THREE.Matrix4();
  detailOn = false;
  lastBakeMs = 0;
  lastDetailMs = 0;

  private readonly baseScene = new THREE.Scene();
  private readonly glowScene = new THREE.Scene();
  private readonly cubeCam: THREE.CubeCamera;
  private readonly detailCam = new THREE.PerspectiveCamera(20, 1, 0.1, 100);
  private readonly uOctaves = { value: 5 };

  constructor(
    objects: SkyObjects,
    readonly quality: BakeQuality,
  ) {
    const opts = { generateMipmaps: true, minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter };
    this.cubeBase = new THREE.WebGLCubeRenderTarget(quality.face, opts);
    this.cubeGlow = new THREE.WebGLCubeRenderTarget(quality.face, opts);
    this.detailBase = new THREE.WebGLRenderTarget(4, 4);
    this.detailGlow = new THREE.WebGLRenderTarget(4, 4);
    this.cubeCam = new THREE.CubeCamera(0.5, 100, this.cubeBase);

    const mw = new THREE.Mesh(
      new THREE.SphereGeometry(10, 64, 32),
      new THREE.ShaderMaterial({
        vertexShader: skyVertex,
        fragmentShader: milkyWayFragment,
        side: THREE.BackSide,
        depthWrite: false,
        depthTest: false,
        uniforms: {
          uOctaves: this.uOctaves,
          uLmc: { value: new THREE.Vector3(...radecToVec(80.894, -69.756)) },
          uSmc: { value: new THREE.Vector3(...radecToVec(13.187, -72.829)) },
        },
      }),
    );
    mw.renderOrder = 0;
    this.baseScene.add(mw, nebulaMesh(objects, true, this.uOctaves));
    this.glowScene.add(nebulaMesh(objects, false, this.uOctaves));
    this.glowScene.background = new THREE.Color(0, 0, 0);
    this.baseScene.background = new THREE.Color(0, 0, 0);
  }

  private step = 0;
  private bakeStart = 0;

  /**
   * Bake one cube face per call (12 calls: 6 base faces, then 6 glow faces), so no single frame
   * holds the GPU long enough to trip a watchdog on phones. Returns true when every face is done.
   */
  bakeStep(gl: THREE.WebGLRenderer): boolean {
    if (this.step >= 12) return true;
    if (this.step === 0) {
      this.bakeStart = performance.now();
      this.cubeCam.coordinateSystem = gl.coordinateSystem;
      this.cubeCam.updateCoordinateSystem();
    }
    const face = this.step % 6;
    const glow = this.step >= 6;
    const rt = glow ? this.cubeGlow : this.cubeBase;
    this.uOctaves.value = this.quality.octaves;
    const prev = gl.getRenderTarget();
    const prevXr = gl.xr.enabled;
    gl.xr.enabled = false;
    // Mipmaps once, after the last face of each cube.
    rt.texture.generateMipmaps = face === 5;
    gl.setRenderTarget(rt, face);
    gl.render(glow ? this.glowScene : this.baseScene, this.cubeCam.children[face] as THREE.Camera);
    rt.texture.generateMipmaps = true;
    gl.setRenderTarget(prev);
    gl.xr.enabled = prevXr;
    this.step++;
    if (this.step === 12) this.lastBakeMs = performance.now() - this.bakeStart;
    return this.step >= 12;
  }

  /** Re-bake a sharp patch for the current view. Call when a zoomed-in view settles. */
  bakeDetail(gl: THREE.WebGLRenderer, view: THREE.PerspectiveCamera, cssWidth: number, cssHeight: number) {
    if (this.step < 12) return;
    const t0 = performance.now();
    const scale = Math.min(1.5, window.devicePixelRatio || 1);
    const w = Math.min(this.quality.detailMax, Math.round(cssWidth * scale * 1.2));
    const h = Math.min(this.quality.detailMax, Math.round(cssHeight * scale * 1.2));
    if (this.detailBase.width !== w || this.detailBase.height !== h) {
      this.detailBase.setSize(w, h);
      this.detailGlow.setSize(w, h);
    }
    // Same orientation as the view, from Earth, with a margin so small pans stay covered.
    this.detailCam.position.set(0, 0, 0);
    this.detailCam.quaternion.copy(view.quaternion);
    this.detailCam.fov = Math.min(view.fov * 1.2, 60);
    this.detailCam.aspect = cssWidth / cssHeight;
    this.detailCam.updateProjectionMatrix();
    this.detailCam.updateMatrixWorld(true);
    this.detailVP.multiplyMatrices(this.detailCam.projectionMatrix, this.detailCam.matrixWorldInverse);

    this.uOctaves.value = this.quality.detailOctaves;
    const prev = gl.getRenderTarget();
    gl.setRenderTarget(this.detailBase);
    gl.render(this.baseScene, this.detailCam);
    gl.setRenderTarget(this.detailGlow);
    gl.render(this.glowScene, this.detailCam);
    gl.setRenderTarget(prev);
    this.detailOn = true;
    this.lastDetailMs = performance.now() - t0;
  }

  dispose() {
    this.cubeBase.dispose();
    this.cubeGlow.dispose();
    this.detailBase.dispose();
    this.detailGlow.dispose();
  }
}
