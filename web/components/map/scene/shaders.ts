// GLSL for the sky shell, catalogue stars, planet hosts, watch bubbles and markers.
// Watches are passed as vec4(direction.xyz, chord radius) where chord = 2 sin(radius / 2):
// comparing chord lengths stays precise down to the 0.05 degree minimum, where cosines do not.

export const MAX_SHADER_WATCHES = 8;

const WATCH_UNIFORMS = /* glsl */ `
  uniform vec4 uWatches[${MAX_SHADER_WATCHES}];
  uniform int uWatchCount;
  uniform vec4 uDraft;
  uniform float uDraftOn;
`;

export const skyVertex = /* glsl */ `
  varying vec3 vDir;
  void main() {
    vDir = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const skyFragment = /* glsl */ `
  precision highp float;
  uniform sampler2D uTex;
  uniform samplerCube uCubeBase;
  uniform samplerCube uCubeGlow;
  uniform sampler2D uDetailBase;
  uniform sampler2D uDetailGlow;
  uniform mat4 uDetailVP;
  uniform float uDetailOn;
  uniform float uArt;
  uniform float uBaked;
  uniform float uTime;
  uniform float uDrift;
  uniform float uZone;
  uniform float uGrounds;
  uniform float uHeat;
  uniform float uTonight;
  uniform float uDraftBlocked;
  uniform vec3 cDeep;
  uniform vec3 cGrid;
  uniform vec3 cRubin;
  uniform vec3 cSolar;
  uniform vec3 cBulge;
  uniform vec3 cHigh;
  uniform vec3 cAccent;
  uniform vec3 cBlocked;
  uniform vec3 cHeatHi;
  ${WATCH_UNIFORMS}
  varying vec3 vDir;

  const float PI = 3.14159265359;
  const float DEG = 0.01745329252;
  const float EPS = 0.40909280422; // obliquity of the ecliptic, J2000

  float capFill(vec3 d, vec4 cap, float fw) {
    return 1.0 - smoothstep(cap.w - fw, cap.w, length(d - cap.xyz));
  }
  float capRing(vec3 d, vec4 cap, float fw) {
    float ch = length(d - cap.xyz);
    return 1.0 - smoothstep(fw * 0.5, fw * 1.4, abs(ch - cap.w));
  }

  void main() {
    vec3 d = normalize(vDir);
    float dec = asin(clamp(d.y, -1.0, 1.0));
    float ra = atan(-d.z, d.x);
    if (ra < 0.0) ra += 2.0 * PI;
    vec4 t = texture2D(uTex, vec2(ra / (2.0 * PI), dec / PI + 0.5));

    vec3 a = vec3(d.x, -d.z, d.y);
    vec3 g = a * mat3(
      -0.0548755604, -0.8734370902, -0.4838350155,
       0.4941094279, -0.44482963,    0.7469822445,
      -0.867666149,  -0.1980763734,  0.4559837762
    );
    float b = asin(clamp(g.z, -1.0, 1.0));
    float l = atan(g.y, g.x);
    float eclLat = asin(clamp(a.z * cos(EPS) - a.y * sin(EPS), -1.0, 1.0));

    vec3 col = cDeep;

    // Illustrated sky (baked). The glow layer drifts very slightly when motion is allowed.
    if (uArt > 0.5 && uBaked > 0.5) {
      vec3 wob = vec3(sin(uTime * 0.11 + d.y * 23.0), sin(uTime * 0.09 + d.z * 19.0), sin(uTime * 0.13 + d.x * 21.0));
      vec3 dg = normalize(d + uDrift * 0.0012 * wob);
      vec3 base = textureCube(uCubeBase, d).rgb;
      vec3 glow = textureCube(uCubeGlow, dg).rgb;
      if (uDetailOn > 0.5) {
        vec4 c = uDetailVP * vec4(d, 1.0);
        if (c.w > 0.0) {
          vec2 ndc = c.xy / c.w;
          float m = max(abs(ndc.x), abs(ndc.y));
          if (m < 1.0) {
            vec2 uv = ndc * 0.5 + 0.5;
            float k = smoothstep(1.0, 0.85, m);
            base = mix(base, texture2D(uDetailBase, uv).rgb, k);
            glow = mix(glow, texture2D(uDetailGlow, uv + uDrift * 0.0006 * wob.xy).rgb, k);
          }
        }
      }
      col += base + glow;
    }

    // Faint RA/Dec grid: Dec every 30 degrees, RA every 2 hours, equator a little stronger.
    float fwDec = fwidth(dec) * 1.1;
    float fwRa = min(fwidth(ra), fwidth(mod(ra + PI, 2.0 * PI))) * 1.1;
    float decLine = 1.0 - smoothstep(0.0, fwDec, abs(mod(dec + 15.0 * DEG, 30.0 * DEG) - 15.0 * DEG));
    float raLine = (1.0 - smoothstep(0.0, fwRa, abs(mod(ra + 15.0 * DEG, 30.0 * DEG) - 15.0 * DEG))) * step(abs(dec), 80.0 * DEG);
    float equator = 1.0 - smoothstep(0.0, fwDec, abs(dec));
    col = mix(col, cGrid, max(max(decLine, raLine) * 0.6, equator) * 0.9);

    // Hunting grounds. The bulge wins where it crosses the ecliptic band.
    if (uGrounds > 0.5) {
      float bd = abs(b) / DEG;
      float ld = abs(l) / DEG;
      float el = abs(eclLat) / DEG;
      float bulge = (1.0 - smoothstep(19.0, 20.0, ld)) * (1.0 - smoothstep(11.5, 12.5, bd));
      float solar = (1.0 - smoothstep(9.5, 10.5, el)) * (1.0 - bulge);
      float high = smoothstep(29.5, 30.5, bd);
      col = mix(col, cBulge, bulge * 0.16);
      col = mix(col, cSolar, solar * 0.13);
      col = mix(col, cHigh, high * 0.07);
      float fwE = fwidth(eclLat);
      col = mix(col, cSolar, (1.0 - smoothstep(0.0, fwE * 1.5, abs(eclLat))) * 0.55);
    }

    // Rubin coverage: a light fill plus a crisp rim where the texture channel crosses 0.5.
    float z = t.r;
    float rim = clamp(z * (1.0 - z) * 4.0, 0.0, 1.0);
    col = mix(col, cRubin, uZone * (0.07 * z + 0.55 * rim));

    // Heatmap.
    float h = t.g;
    col = mix(col, mix(cRubin, cHeatHi, h), uHeat * smoothstep(0.02, 1.0, h) * 0.8);

    // Rubin tonight fields.
    float tb = t.b;
    float tr = clamp(tb * (1.0 - tb) * 4.0, 0.0, 1.0);
    col = mix(col, cHeatHi, uTonight * (0.08 * tb + 0.7 * tr));

    // Watches.
    for (int i = 0; i < ${MAX_SHADER_WATCHES}; i++) {
      if (i >= uWatchCount) break;
      float fw = fwidth(length(d - uWatches[i].xyz));
      col = mix(col, cAccent, capFill(d, uWatches[i], fw) * 0.1 + capRing(d, uWatches[i], fw) * 0.9);
    }

    // The watch being drawn.
    if (uDraftOn > 0.5) {
      vec3 dc = mix(cAccent, cBlocked, uDraftBlocked);
      float fw = fwidth(length(d - uDraft.xyz));
      col = mix(col, dc, capFill(d, uDraft, fw) * 0.14 + capRing(d, uDraft, fw));
    }

    gl_FragColor = vec4(col, 1.0);
  }
`;

/** Planet hosts: 3D positions, drawn in the accent colour. */
export const hostVertex = /* glsl */ `
  attribute float aSize;
  uniform float uPx;
  ${WATCH_UNIFORMS}
  varying float vHi;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    vec3 dir = normalize(position);
    float hi = 0.0;
    for (int i = 0; i < ${MAX_SHADER_WATCHES}; i++) {
      if (i >= uWatchCount) break;
      if (length(dir - uWatches[i].xyz) < uWatches[i].w) hi = 1.0;
    }
    if (uDraftOn > 0.5 && length(dir - uDraft.xyz) < uDraft.w) hi = 1.0;
    float size = clamp((1.6 + aSize * 0.45) * 150.0 / max(-mv.z, 1.0), 2.4, 7.0);
    gl_PointSize = (size + hi * 3.0) * uPx;
    vHi = hi;
  }
`;

export const hostFragment = /* glsl */ `
  precision mediump float;
  uniform vec3 cAccent;
  varying float vHi;
  void main() {
    vec2 p = gl_PointCoord * 2.0 - 1.0;
    float r = length(p);
    if (r > 1.0) discard;
    // A small dark halo keeps hosts readable over the brightest part of the Milky Way.
    float disc = 1.0 - smoothstep(0.55, 0.7, r);
    float halo = (1.0 - smoothstep(0.7, 1.0, r)) * (1.0 - disc);
    vec3 col = mix(cAccent, vec3(1.0), vHi * 0.6);
    gl_FragColor = vec4(col * disc, max(disc, halo * 0.55));
  }
`;

/** Bright catalogue stars, painted on the sky sphere for orientation. */
export const starVertex = /* glsl */ `
  attribute float aMag;
  attribute vec3 aColor;
  uniform float uPx;
  uniform float uFovScale;
  varying vec3 vColor;
  varying float vA;
  void main() {
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    float s = clamp(5.4 - 0.72 * aMag, 1.1, 5.5) * uFovScale;
    gl_PointSize = s * uPx;
    vColor = aColor;
    vA = clamp(1.25 - aMag * 0.14, 0.3, 1.0);
  }
`;

export const starFragment = /* glsl */ `
  precision mediump float;
  varying vec3 vColor;
  varying float vA;
  void main() {
    vec2 p = gl_PointCoord * 2.0 - 1.0;
    float r2 = dot(p, p);
    if (r2 > 1.0) discard;
    float a = exp(-r2 * 4.0) * vA;
    gl_FragColor = vec4(vColor * a, a);
  }
`;

export const bubbleVertex = /* glsl */ `
  varying vec3 vN;
  varying vec3 vV;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vN = normalize(normalMatrix * normal);
    vV = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

export const bubbleFragment = /* glsl */ `
  precision mediump float;
  uniform vec3 uColor;
  uniform float uOpacity;
  varying vec3 vN;
  varying vec3 vV;
  void main() {
    float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.5);
    gl_FragColor = vec4(uColor, (0.03 + 0.4 * f) * uOpacity);
  }
`;

export const markerVertex = /* glsl */ `
  uniform float uPx;
  attribute float aBlocked;
  varying float vBlocked;
  void main() {
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = 20.0 * uPx;
    vBlocked = aBlocked;
  }
`;

export const markerFragment = /* glsl */ `
  precision mediump float;
  uniform vec3 cAccent;
  uniform vec3 cBlocked;
  varying float vBlocked;
  void main() {
    vec2 p = gl_PointCoord * 2.0 - 1.0;
    // Four short ticks around the centre: findable at any zoom, even when the cap itself is sub-pixel.
    float r = length(p);
    float tick = step(0.45, r) * step(r, 0.95) * (step(abs(p.x), 0.05) + step(abs(p.y), 0.05));
    float a = min(tick, 1.0);
    if (a < 0.01) discard;
    gl_FragColor = vec4(mix(cAccent, cBlocked, vBlocked), a);
  }
`;
