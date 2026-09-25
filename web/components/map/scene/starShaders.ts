// GLSL for stars: far-away point sprites (catalogue stars and planet hosts), and the close-up of the
// focused star (animated surface sphere + corona billboard). Colours arrive linear; the bloom
// composer encodes to sRGB on output. Values above 1 are what the bloom pass picks up.

import { noiseGlsl } from "./noise";
import { MAX_SHADER_WATCHES } from "./shaders";

/**
 * Point sprite: a sharp core plus a soft gaussian halo, sized from apparent magnitude and drawn in
 * device pixels so it stays crisp at any DPR. Additive. Hosts also get:
 *   - a proximity boost (brighter as the camera approaches, never dimmer than from Earth);
 *   - an accent ring for hover, selection and watched hosts;
 *   - a fade for the focused star as it swaps to the close-up sphere.
 */
export const spriteVertex = /* glsl */ `
  attribute vec3 aColor;
  attribute float aMag;
  attribute float aIndex;
  uniform float uPx;
  uniform float uFovScale;
  uniform float uMinI;
  uniform float uProximity;
  uniform float uHover;
  uniform float uHoverT;
  uniform float uSelected;
  uniform float uSelectedT;
  uniform float uFocusFade;
  uniform float uRings;
  uniform vec4 uWatches[${MAX_SHADER_WATCHES}];
  uniform int uWatchCount;
  uniform vec4 uDraft;
  uniform float uDraftOn;
  varying vec3 vColor;
  varying float vI;
  varying float vCore;
  varying float vHalo;
  varying float vRing;
  varying float vRingA;
  varying float vSize;

  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;

    float m = aMag;
    if (uProximity > 0.5) {
      // Scene-space inverse square law, only ever brightening: from Earth you see the catalogue magnitude.
      float fromEarth = length(position);
      float fromCam = max(-mv.z, 1e-5);
      m -= 5.0 * log(max(fromEarth / fromCam, 1.0)) / log(10.0);
    }

    // Brightness relative to a 4th magnitude star. Floor keeps faint stars as visible pin-pricks.
    float I = clamp(pow(10.0, -0.4 * (m - 4.0)), uMinI, 8.0);
    float core = clamp(1.9 - 0.16 * m, 0.6, 2.6) * uFovScale;     // CSS px radius
    float halo = (1.0 + 1.5 * sqrt(min(I, 8.0))) * uFovScale;       // CSS px gaussian sigma

    float isHover = step(abs(aIndex - uHover), 0.5) * uHoverT;
    float isSel = step(abs(aIndex - uSelected), 0.5) * uSelectedT;
    float watched = 0.0;
    vec3 dir = normalize(position);
    for (int i = 0; i < ${MAX_SHADER_WATCHES}; i++) {
      if (i >= uWatchCount) break;
      if (length(dir - uWatches[i].xyz) < uWatches[i].w) watched = 1.0;
    }
    if (uDraftOn > 0.5 && length(dir - uDraft.xyz) < uDraft.w) watched = 1.0;
    float ringA = max(max(isHover, isSel), watched * 0.55) * uRings;
    float ring = core + 5.0;

    float fade = 1.0 - step(abs(aIndex - uSelected), 0.5) * uFocusFade;
    vColor = aColor;
    vI = I * fade;
    vCore = core * uPx;
    vHalo = halo * uPx;
    vRing = ring * uPx;
    vRingA = ringA * fade;
    float radius = max(halo * 2.6, ringA > 0.0 ? ring + 1.5 : 0.0);
    vSize = radius * uPx;
    gl_PointSize = 2.0 * vSize;
    if (fade < 0.01) gl_PointSize = 0.0;
  }
`;

export const spriteFragment = /* glsl */ `
  precision highp float;
  uniform vec3 cAccent;
  varying vec3 vColor;
  varying float vI;
  varying float vCore;
  varying float vHalo;
  varying float vRing;
  varying float vRingA;
  varying float vSize;

  void main() {
    float r = length(gl_PointCoord * 2.0 - 1.0) * vSize; // device px from centre
    // Sharp core: a disc anti-aliased over one device pixel, never smaller than a pixel.
    float core = 1.0 - smoothstep(max(vCore - 0.5, 0.0), vCore + 0.5, r);
    float halo = exp(-0.5 * (r * r) / (vHalo * vHalo));
    // Hot centre: the core runs white-ish above 1, so bright stars bloom and faint ones do not.
    vec3 c = vColor * (core * (0.55 + 0.9 * vI) + halo * 0.32 * vI);
    float ring = (1.0 - smoothstep(0.0, 1.0, abs(r - vRing))) * vRingA;
    c += cAccent * ring * 0.85;
    if (max(max(c.r, c.g), c.b) < 0.002) discard;
    gl_FragColor = vec4(c, 1.0);
  }
`;

/** Close-up star surface, on a unit sphere scaled to the star's display radius. */
export const surfaceVertex = /* glsl */ `
  varying vec3 vObj;
  varying vec3 vN;
  varying vec3 vV;
  void main() {
    vObj = position;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vN = normalize(normalMatrix * normal);
    vV = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

export function surfaceFragment(octaves: number) {
  return /* glsl */ `
  precision highp float;
  ${noiseGlsl}
  uniform vec3 uColor;     // linear, peak channel 1
  uniform vec3 uLimbColor; // a slightly cooler colour for the limb
  uniform float uHot;      // 0 = 2500 K red dwarf .. 1 = 12000 K and hotter
  uniform float uLimb;     // linear limb darkening coefficient
  uniform float uTime;
  uniform float uSeed;
  uniform float uOpacity;
  varying vec3 vObj;
  varying vec3 vN;
  varying vec3 vV;

  float fbmN(vec3 p) {
    float a = 0.5;
    float s = 0.0;
    for (int i = 0; i < ${octaves}; i++) {
      s += a * snoise(p);
      p = p * 2.03 + 11.7;
      a *= 0.5;
    }
    return s;
  }

  void main() {
    vec3 p = normalize(vObj);
    float mu = clamp(dot(normalize(vN), normalize(vV)), 0.0, 1.0);
    float t = uTime;

    // Convection granulation: bright rising cells, darker sinking lanes. Larger, fewer cells for cool
    // stars; finer for hot ones. Domain warping makes the pattern boil slowly.
    float scale = mix(16.0, 34.0, uHot);
    vec3 q = p * scale + uSeed;
    vec3 warp = vec3(snoise(q * 0.3 + vec3(0.0, 0.0, t * 0.05)), snoise(q * 0.3 + vec3(13.1, 0.0, -t * 0.04)), snoise(q * 0.3 + vec3(0.0, 27.3, t * 0.045)));
    float n = snoise(q + warp * 0.8 + vec3(t * 0.03));
    float cells = smoothstep(-0.55, 0.65, n);
    float lanes = 1.0 - 0.22 * (1.0 - smoothstep(0.0, 0.1, abs(n + 0.15)));
    float detail = fbmN(q * 2.1 + warp * 0.4 - vec3(t * 0.02));
    float gran = (0.74 + 0.3 * cells + 0.08 * detail) * lanes;

    // Supergranulation and a few dark spots (low frequency, high threshold), drifting very slowly.
    float sup = snoise(p * 2.2 + uSeed * 0.3 + vec3(t * 0.006));
    float spotN = snoise(p * 1.7 + vec3(uSeed * 1.7, 0.0, t * 0.004));
    float spotF = snoise(p * 5.0 + vec3(0.0, uSeed, 0.0));
    float spotV = spotN * 0.8 + spotF * 0.25;
    float spot = smoothstep(0.74, 0.8, spotV);
    float penumbra = smoothstep(0.66, 0.76, spotV);

    // Linear limb darkening: I(mu) = 1 - u (1 - mu).
    float limb = 1.0 - uLimb * (1.0 - mu);
    float I = limb * gran * (1.0 + 0.08 * sup) * (1.0 - 0.3 * penumbra) * (1.0 - 0.45 * spot);
    vec3 col = mix(uLimbColor, uColor, smoothstep(0.0, 0.7, mu));
    // Emissive, not lit: HDR toward the centre, then a soft per-channel shoulder so the hottest
    // regions run toward white (molten) while the limb keeps the star's colour.
    vec3 hdr = col * I * mix(1.1, mix(1.55, 2.4, uHot), mu);
    col = 1.35 * (1.0 - exp(-hdr));
    gl_FragColor = vec4(col, uOpacity);
  }
`;
}

/** Corona / halo billboard: a camera-facing quad centred on the star, fresnel-like falloff from the limb. */
export const coronaVertex = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv * 2.0 - 1.0;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const coronaFragment = /* glsl */ `
  precision highp float;
  ${noiseGlsl}
  uniform vec3 uColor;
  uniform float uExtent;   // quad half-size in stellar radii
  uniform float uTime;
  uniform float uSeed;
  uniform float uOpacity;
  varying vec2 vUv;

  void main() {
    float r = length(vUv) * uExtent; // in stellar radii
    if (r < 0.98 || r > uExtent) discard;
    float x = r - 1.0;
    // Fresnel-like: brightest right at the limb, then a tight falloff and a long faint tail.
    float rim = exp(-x * 14.0);
    float tail = exp(-x * 2.6) * 0.35;
    float a = atan(vUv.y, vUv.x);
    float streak = 0.8 + 0.35 * snoise(vec3(cos(a) * 2.2, sin(a) * 2.2, uSeed + uTime * 0.02 - x * 0.6));
    float edge = 1.0 - smoothstep(uExtent * 0.7, uExtent, r);
    float I = (rim * 1.3 + tail * streak) * edge * smoothstep(0.98, 1.0, r);
    gl_FragColor = vec4(uColor * I * uOpacity, 1.0);
  }
`;
