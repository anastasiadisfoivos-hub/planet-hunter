"""Light-curve, check-table and pixel-map graphics for the candidate report, drawn from public/data/finder/c/*.json."""
import json, statistics, random, math, os

WEB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))
d = json.load(open(f'{WEB}/public/data/finder/c/tic219345170-01.json'))
c = d['candidate']
px = d['pixels']['images']
P = c['period_d']


def frame(W, H, xticks, xtitle):
    """Axes for a chart whose viewBox width equals its rendered width, so 11 units = 11px."""
    L, T, R, B = 40, 10, 6, 40
    pw, ph = W - L - R, H - T - B
    yv = lambda f: T + (0.1 - (f - 1) * 100) / 0.4 * ph
    out = []
    for v in (0, -0.1, -0.2):
        y = yv(1 + v / 100)
        out.append(f'<path d="M{L} {y:.1f}H{L+pw}" stroke="rgb(222 230 255 / {".16" if v == 0 else ".06"})"/>')
        lab = '0%' if v == 0 else f'{v:g}%'
        out.append(f'<text x="{L-8}" y="{y+4:.1f}" text-anchor="end">{lab}</text>')
    for x, lab in xticks:
        out.append(f'<text x="{x:.1f}" y="{T+ph+18}" text-anchor="middle">{lab}</text>')
    out.append(f'<text class="t" x="{L+pw}" y="{T+ph+36}" text-anchor="end">{xtitle}</text>')
    return L, T, pw, ph, yv, out


def fold(W=346, H=250):
    X = None
    L, T, pw, ph, yv, out = 0, 0, 0, 0, None, None
    L, T, pw, ph, yv, out = frame(W, H, [], 'Hours from mid-dip')
    X = lambda h: L + (h + 7) / 14 * pw
    out[-1:-1] = [f'<text x="{X(h):.1f}" y="{T+ph+18}" text-anchor="middle">{("+" if h > 0 else "") + str(h)}</text>' for h in (-6, -3, 0, 3, 6)]
    pts = [(p * P * 24, f) for p, f in zip(c['folded']['phase'], c['folded']['flux']) if abs(p * P * 24) <= 7]
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Folded light curve: a flat-bottomed dip of 0.18 percent lasting 2.9 hours">']
    s.append(f'<rect x="{X(-1.45):.1f}" y="{T}" width="{X(1.45)-X(-1.45):.1f}" height="{ph}" fill="rgb(222 230 255 / .05)"/>')
    s += out
    s.append('<g fill="#8B909A" fill-opacity=".6">' + ''.join(f'<circle cx="{X(h):.1f}" cy="{min(T+ph, yv(f)):.1f}" r="1.2"/>' for h, f in pts) + '</g>')
    b = {}
    for h, f in pts:
        b.setdefault(round(h * 2) / 2, []).append(f)
    med = [(X(k), yv(statistics.median(v))) for k, v in sorted(b.items())]
    s.append('<path fill="none" stroke="#F4F4F5" stroke-width="1.5" stroke-linejoin="round" d="M' + ' L'.join(f'{x:.1f} {y:.1f}' for x, y in med) + '"/>')
    s.append('</svg>')
    return ''.join(s)


def full(W=486, H=250, step=10, n=1400):
    t = c['unfolded']['time_btjd']; f = c['unfolded']['flux']; t0, t1 = 3507, 3563
    L, T, pw, ph, yv, out = frame(W, H, [], 'Days (BTJD)')
    X = lambda x: L + (x - t0) / (t1 - t0) * pw
    out[-1:-1] = [f'<text x="{X(x):.1f}" y="{T+ph+18}" text-anchor="middle">{x}</text>' for x in range(3510, 3561, step)]
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Whole light curve over 55 days, with 13 dips at the predicted times">']
    s += out
    random.seed(2)
    idx = sorted(random.sample(range(len(t)), min(n, len(t))))
    s.append('<g fill="#8B909A" fill-opacity=".5">' + ''.join(f'<circle cx="{X(t[i]):.1f}" cy="{max(T, min(T+ph, yv(f[i]))):.1f}" r="0.9"/>' for i in idx) + '</g>')
    ticks, k = [], 0
    while True:
        tt = c['t0_btjd'] + k * P
        if tt > t1:
            break
        if tt >= t0:
            ticks.append(X(tt))
        k += 1
    s.append('<g stroke="#F4F4F5">' + ''.join(f'<path d="M{x:.1f} {T}v7"/>' for x in ticks) + '</g>')
    s.append('</svg>')
    return ''.join(s)


NAMES = {'snr': 'Signal strength', 'odd_even': 'Odd and even dips match', 'secondary_eclipse': 'No second dip halfway round',
         'size': 'Planet-sized', 'transit_count': 'Enough dips', 'depth_consistency': 'Same depth every sector'}


def val(ch):
    n, v = ch['name'], ch['value']
    return {'snr': f'<span class="num">{v}</span><span class="unit">× noise</span>',
            'odd_even': f'<span class="num">{v}σ</span><span class="unit">apart</span>',
            'secondary_eclipse': f'<span class="num">{v}σ</span>',
            'size': f'<span class="num">{v*11.21:.1f}</span><span class="unit">R⊕</span>',
            'transit_count': f'<span class="num">{v}</span><span class="unit">dips</span>',
            'depth_consistency': f'<span class="num">{v}σ</span><span class="unit">change</span>'}[n]


def checks():
    icon = ('<svg width="16" height="16" viewBox="0 0 16 16" role="img" aria-label="Passed"><circle cx="8" cy="8" r="6.75" fill="none" '
            'stroke="#A1A6B0" stroke-width="1.25"/><path d="M5.2 8.2l1.9 1.9 3.8-4" fill="none" stroke="#F4F4F5" stroke-width="1.5" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    rows = []
    for ch in c['checks']:
        r = ch['reason']
        if ch['name'] == 'size':
            r = "Depth 0.184% on a star 0.94 times the Sun's size gives 4.4 Earth radii (likely 3.7 to 5.0). That is within the size range of planets."
        rows.append(f'<tr><td class="st">{icon}</td><td class="nm">{NAMES[ch["name"]]}</td><td class="val">{val(ch)}</td><td class="why">{r}</td></tr>')
    return '\n          '.join(rows)


def heat(grid, diff):
    n = len(grid); cs = 24
    s = [f'<svg viewBox="0 0 {n*cs} {n*cs}" role="img" aria-label="{"Difference image: the missing light is centred on the target" if diff else "TESS pixels between dips"}">']
    vals = [v for r in grid for v in r]
    if diff:
        m = max(abs(v) for v in vals)
    else:
        lo, hi = math.log10(max(min(vals), 0.5)), math.log10(max(vals))
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if diff:
                a = max(-1, min(1, v / m)); col = (242, 193, 78) if a > 0 else (124, 196, 242); k = abs(a) ** 0.8
                r, g, b = [round(17 + (cc - 17) * k) for cc in col]
            else:
                k = (math.log10(max(v, 0.5)) - lo) / (hi - lo); g = round(17 + 238 * max(0, min(1, k)) ** 1.2); r = b = g
            s.append(f'<rect x="{x*cs}" y="{y*cs}" width="{cs}" height="{cs}" fill="rgb({r},{g},{b})"/>')
    for mk in px['markers']:
        cx = min(n * cs - 8, max(8, mk['x'] * cs + cs / 2)); cy = min(n * cs - 8, max(8, mk['y'] * cs + cs / 2))
        if mk['kind'] == 'target':
            s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="none" stroke="#000" stroke-width="3"/><circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="none" stroke="#F4F4F5" stroke-width="1.5"/>')
        else:
            dpath = f'M{cx:.1f} {cy-6:.1f}l6 6-6 6-6-6z'
            s.append(f'<path d="{dpath}" fill="none" stroke="#000" stroke-width="3"/><path d="{dpath}" fill="none" stroke="#F4F4F5" stroke-width="1.25"/>')
    if diff:
        cx, cy = px['centroid']['x'] * cs + cs / 2, px['centroid']['y'] * cs + cs / 2
        plus = f'M{cx-7:.1f} {cy:.1f}h14M{cx:.1f} {cy-7:.1f}v14'
        s.append(f'<path d="{plus}" stroke="#000" stroke-width="3.5"/><path d="{plus}" stroke="#F4F4F5" stroke-width="1.5"/>')
    s.append('</svg>')
    return ''.join(s)


