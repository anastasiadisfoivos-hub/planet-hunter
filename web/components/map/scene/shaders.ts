// GLSL for the sky shell (grid, Rubin coverage, heatmap, the selected event's error circle),
// Earth, and the event markers. Caps are vec4(direction.xyz, chord) with chord = 2 sin(radius / 2):
// comparing chord lengths stays precise at tiny radii, where cosines do not.

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
  uniform float uHeat;
  uniform vec4 uSel;
  uniform float uSelOn;
  uniform vec3 cDeep;
  uniform vec3 cGrid;
  uniform vec3 cRubin;
  uniform vec3 cAccent;
  uniform vec3 cHeatHi;
  varying vec3 vDir;

  const float PI = 3.14159265359;
  const float DEG = 0.01745329252;

  void main() {
    vec3 d = normalize(vDir);
    float dec = asin(clamp(d.y, -1.0, 1.0));
    float ra = atan(-d.z, d.x);
    if (ra < 0.0) ra += 2.0 * PI;
    vec4 t = texture2D(uTex, vec2(ra / (2.0 * PI), dec / PI + 0.5));

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

    // Rubin coverage: the texture holds a blurred inside/outside field, so its 0.5 contour is a smooth
    // curve. Draw that contour as an anti-aliased hairline plus a very light fill.
    float z = t.r;
    float fwz = max(fwidth(z), 1e-4);
    float rim = 1.0 - smoothstep(0.0, fwz * 1.3, abs(z - 0.5));
    float fill = smoothstep(0.35, 0.65, z);
    col = mix(col, cRubin, uZone * (0.045 * fill + 0.5 * rim));

    // Rubin alerts heatmap.
    float h = t.g;
    col = mix(col, mix(cRubin, cHeatHi, h), uHeat * smoothstep(0.02, 1.0, h) * 0.8);

    // The selected event's error circle.
    if (uSelOn > 0.5) {
      float ch = length(d - uSel.xyz);
      float fw = fwidth(ch);
      float ring = 1.0 - smoothstep(fw * 0.5, fw * 1.4, abs(ch - uSel.w));
      float inside = 1.0 - smoothstep(uSel.w - fw, uSel.w, ch);
      col = mix(col, cAccent, inside * 0.08 + ring * 0.85);
    }

    // Every layer above was tuned as display values. The bloom composer encodes to sRGB on output, so
    // decode once here: overlays keep their tuned (subtle) strength on the black sky.
    gl_FragColor = vec4(pow(col, vec3(2.2)), 1.0);
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

/**
 * Event markers: one point per event, the shape and colour of its category. Recent events are
 * larger and brighter. Hover and selection add an accent ring. Drawn in device pixels, on top.
 */
export const eventVertex = /* glsl */ `
  attribute vec3 aColor;
  attribute float aShape;
  attribute float aRecency;
  attribute float aIndex;
  uniform float uPx;
  uniform float uHover;
  uniform float uHoverT;
  uniform float uSelected;
  uniform float uDim;
  varying vec3 vColor;
  varying float vShape;
  varying float vA;
  varying float vRing;
  varying float vSize;
  varying float vMark;
  void main() {
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    float hov = step(abs(aIndex - uHover), 0.5) * uHoverT;
    float sel = step(abs(aIndex - uSelected), 0.5);
    float ring = max(hov, sel);
    // 11 px for a 30-day-old event, 17 px for one from the last hours.
    float mark = mix(11.0, 17.0, (aRecency - 0.35) / 0.65) + 3.0 * ring;
    vMark = mark * uPx;
    vSize = (mark + 12.0) * uPx;
    gl_PointSize = vSize;
    vColor = aColor;
    vShape = aShape;
    vA = mix(0.55, 1.0, (aRecency - 0.35) / 0.65) * mix(1.0, 0.35, uDim * (1.0 - ring));
    vRing = ring;
  }
`;

export const eventFragment = /* glsl */ `
  precision highp float;
  uniform vec3 cAccent;
  varying vec3 vColor;
  varying float vShape;
  varying float vA;
  varying float vRing;
  varying float vSize;
  varying float vMark;

  // Signed distances in device pixels (negative inside).
  float sdCircle(vec2 p, float r) { return length(p) - r; }
  float sdBox(vec2 p, float r) { vec2 q = abs(p) - vec2(r); return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0); }
  float sdDiamond(vec2 p, float r) { return (abs(p.x) + abs(p.y) - r) * 0.7071; }
  // Equilateral triangle (Inigo Quilez), pointing up.
  float sdTriangle(vec2 p, float r) {
    const float k = 1.7320508;
    p.x = abs(p.x) - r;
    p.y = p.y + r / k;
    if (p.x + k * p.y > 0.0) p = vec2(p.x - k * p.y, -k * p.x - p.y) / 2.0;
    p.x -= clamp(p.x, -2.0 * r, 0.0);
    return -length(p) * sign(p.y);
  }
  float sdPlus(vec2 p, float r, float w) {
    p = abs(p);
    return min(max(p.x - r, p.y - w), max(p.x - w, p.y - r));
  }

  void main() {
    vec2 p = (gl_PointCoord * 2.0 - 1.0) * vSize * 0.5;
    p.y = -p.y;
    float r = vMark * 0.5;
    float line = 1.6 * (vSize / (vMark + 12.0)); // 1.6 CSS px stroke
    float d;
    int s = int(vShape + 0.5);
    if (s == 0) d = abs(sdCircle(p, r - line)) - line * 0.5;          // ring
    else if (s == 1) d = abs(sdDiamond(p, r)) - line * 0.5;           // diamond outline
    else if (s == 2) d = abs(sdBox(p, r * 0.78)) - line * 0.5;        // square outline
    else if (s == 3) d = abs(sdTriangle(p, r * 0.9)) - line * 0.5;    // triangle outline
    else if (s == 4) d = sdPlus(p, r, line * 0.6);                   // plus
    else d = sdCircle(p, r * 0.32);                                  // dot
    // A filled centre point for the outline shapes, so position reads at a glance.
    float centre = s == 4 || s == 5 ? 1e9 : sdCircle(p, line * 0.8);
    float shape = 1.0 - smoothstep(-0.5, 0.5, min(d, centre));
    // A black halo keeps markers legible over bright stars and the Milky Way.
    float halo = 1.0 - smoothstep(-0.5, 1.5, min(d, centre) - line * 1.2);
    float ringD = abs(length(p) - (r + line * 2.6)) - line * 0.5;
    float ring = (1.0 - smoothstep(-0.5, 0.5, ringD)) * vRing;
    vec3 col = vColor * shape * vA + cAccent * ring;
    float a = max(max(shape * vA, ring), halo * 0.6 * vA);
    if (a < 0.003) discard;
    gl_FragColor = vec4(col, a);
  }
`;
