"""Build the POLISH v2 static mocks from the app's own data and the credited pictures in web/public/images/.

    python3 docs/polish/mocks-v2/build.py [path/to/eso0932a-large.jpg]

Serve web/ (python3 -m http.server) and open /docs/polish/mocks-v2/<page>.html. Every picture is real:
credits.json holds its source, credit and licence. The only drawn things are data graphics (light curves, pixel
maps) and the constellation lines (d3-celestial, BSD-3-Clause, data/LICENSE-d3-celestial.txt).
"""
import html, json, math, os, statistics, sys
from datetime import datetime, timedelta, timezone
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.abspath(os.path.join(HERE, '../../..'))
IMG = f'{WEB}/public/images'
REL = '../../../public/images'          # from the mock pages to public/images
credits = json.load(open(f'{IMG}/credits.json'))
events_all = json.load(open(f'{WEB}/public/data/events.mock.json'))['events']
hosts = json.load(open(f'{WEB}/public/data/hosts.json'))
cand_index = json.load(open(f'{WEB}/public/data/finder/index.mock.json'))
NOW = datetime(2026, 9, 25, 16, 3, tzinfo=timezone.utc)
esc = html.escape

CATEGORIES = {
    'transients': ['supernova', 'tidal_disruption_event', 'kilonova', 'nova', 'active_galaxy_flare', 'variable_star', 'stellar_flare', 'microlensing'],
    'solar_system': ['asteroid', 'near_earth_object', 'comet', 'interstellar_object'],
    'sun_space_weather': ['solar_flare', 'coronal_mass_ejection', 'geomagnetic_storm'],
    'earth_atmosphere': ['fireball'],
    'high_energy': ['gamma_ray_burst', 'neutrino', 'gravitational_wave'],
    'other': ['unknown'],
}
CAT_OF = {t: c for c, ts in CATEGORIES.items() for t in ts}
CHIP = {'transients': 'Transients', 'solar_system': 'Solar system', 'sun_space_weather': 'Sun', 'earth_atmosphere': 'Earth', 'high_energy': 'Energy', 'other': 'Other'}
TYPE_LABEL = {'supernova': 'Supernova', 'tidal_disruption_event': 'Tidal disruption', 'kilonova': 'Kilonova', 'nova': 'Nova',
              'active_galaxy_flare': 'Active galaxy flare', 'variable_star': 'Variable star', 'stellar_flare': 'Stellar flare',
              'microlensing': 'Microlensing', 'asteroid': 'Asteroid', 'near_earth_object': 'Near-Earth object', 'comet': 'Comet',
              'interstellar_object': 'Interstellar object', 'gamma_ray_burst': 'Gamma-ray burst', 'neutrino': 'Neutrino',
              'gravitational_wave': 'Gravitational wave', 'fireball': 'Fireball', 'solar_flare': 'Solar flare',
              'coronal_mass_ejection': 'Coronal mass ejection', 'geomagnetic_storm': 'Geomagnetic storm', 'unknown': 'Unclassified'}
SOURCE = {'rubin': 'Rubin', 'ztf': 'ZTF', 'tns': 'TNS', 'mpc': 'MPC', 'jpl': 'JPL', 'cneos': 'CNEOS', 'donki': 'NASA DONKI',
          'gcn': 'GCN', 'icecube': 'IceCube', 'gracedb': 'GraceDB'}
COLOR = {'transients': 'var(--cat-transient)', 'solar_system': 'var(--cat-solar-system)', 'sun_space_weather': 'var(--cat-sun)',
         'earth_atmosphere': 'var(--cat-earth)', 'high_energy': 'var(--cat-high-energy)', 'other': 'var(--cat-other)'}
MON = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


def glyph(cat, size=10, stroke=1.5):
    c = COLOR[cat]; s = size; m = s / 2
    shape = {
        'transients': f'<circle cx="{m}" cy="{m}" r="{m-1.2}" fill="none" stroke="{c}" stroke-width="{stroke}"/>',
        'solar_system': f'<path d="M{m} 0.8 {s-0.8} {m} {m} {s-0.8} 0.8 {m}z" fill="none" stroke="{c}" stroke-width="{stroke}"/>',
        'sun_space_weather': f'<rect x="1.2" y="1.2" width="{s-2.4}" height="{s-2.4}" fill="none" stroke="{c}" stroke-width="{stroke}"/>',
        'earth_atmosphere': f'<path d="M{m} 1.2 {s-1} {s-1.2}H1z" fill="{c}"/>',
        'high_energy': f'<path d="M{m} 0.8v{s-1.6}M0.8 {m}h{s-1.6}" stroke="{c}" stroke-width="{stroke}"/>',
        'other': f'<circle cx="{m}" cy="{m}" r="{s*0.22:.1f}" fill="{c}"/>',
    }[cat]
    return f'<svg width="{s}" height="{s}" viewBox="0 0 {s} {s}" aria-hidden="true" style="flex:none">{shape}</svg>'


def day(iso):
    d = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    return f'{d.day} {MON[d.month-1]}'


def hhmm(iso):
    return iso[11:16] + ' UTC'


def img_rel(e):
    sid = e['id'].replace(':', '-').replace('/', '-').replace(' ', '_')
    rel = f'events/{sid}.jpg'
    return rel if rel in credits else None


def short_name(e):
    t = e['title']
    for p in ('Supernova candidate ', 'Variable star candidate ', 'Possible near-Earth object ', 'Possible comet ',
              'Gamma-ray burst ', 'Coronal mass ejection ', 'Transient candidate ', 'Active galaxy flare candidate '):
        if t.startswith(p):
            t = t[len(p):]
    if e['type'] == 'coronal_mass_ejection':
        t = 'CME ' + t.strip('()')
    return t.replace(' (known asteroid)', '').replace(' (blazar in high state)', '').replace(' (TNS nova)', '').replace(' (TNS TDE)', '')


def flag(e, rel):
    if rel and credits[rel].get('archive'):
        return 'Archive'
    if e['confidence_basis'] == 'machine_guess':
        return f'Guess {round(e["confidence"]*100)}%'
    return hhmm(e['observed_at']) if e['type'] not in ('near_earth_object', 'comet') else day(e['observed_at'])


def info(rel, extra=''):
    c = credits[rel]
    return (f'<details class="info"><summary aria-label="About this picture">i</summary><div class="pop">'
            f'<div style="color:var(--ink)">{esc(c["title"])}</div><div style="margin-top:8px">{esc(c["credit"])}</div>'
            f'<div style="margin-top:4px">{esc(c["licence"])}</div>{extra}'
            f'<a href="{esc(c["url"])}" style="display:inline-block;margin-top:8px;color:var(--ink)">Source ↗</a></div></details>')


def src_short(rel):
    c = credits[rel]
    s = c['credit']
    for k, v in (('DESI Legacy', 'DESI Legacy Surveys'), ('Pan-STARRS', 'Pan-STARRS1'), ('SkyMapper', 'SkyMapper'),
                 ('Digitized Sky', 'DSS2'), ('NASA/SDO', 'NASA SDO/AIA'), ('Courtesy of NASA/SDO', 'NASA SDO/AIA'),
                 ('Rubin', 'Rubin Observatory'), ('ZTF', 'ZTF'), ('ESO/', 'ESO'), ('STScI', 'NASA · ESA'), ('JPL', 'NASA/JPL')):
        if k in s:
            return v
    return s.split(',')[0][:28]


def topbar(active, over=False):
    links = ''.join(f'<a href="{h}"{" aria-current=\"page\"" if n == active else ""}>{n}</a>'
                    for n, h in (('Events', 'events.html'), ('Sky', 'sky.html'), ('Lab', 'lab.html'), ('Finder', 'finder.html')))
    return (f'<header class="topbar{" over" if over else ""}"><div class="wrap">'
            '<a class="wordmark" href="home.html"><svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7.25" fill="none" stroke="#F4F4F5" stroke-width="1.5"/><circle cx="8" cy="8" r="2.5" fill="#F4F4F5"/></svg><span>Planet Hunter</span></a>'
            f'<nav class="nav" aria-label="Main">{links}</nav>'
            '<div class="end"><a class="find" href="#" aria-label="Find a star"><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M11 11l3.5 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg><span>Find a star</span></a></div>'
            '</div></header>')


def page(title, body, css=''):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f'<title>{esc(title)} (POLISH v2 mock)</title><link rel="stylesheet" href="v2.css"><style>{css}</style></head><body>{body}</body></html>')


def week():
    lo = NOW - timedelta(days=7)
    ev = [e for e in events_all if lo <= datetime.fromisoformat(e['observed_at'].replace('Z', '+00:00')) <= NOW]
    return sorted(ev, key=lambda e: e['observed_at'], reverse=True)


def tile(href, pic, name, cap, extra='', cls=''):
    """A picture tile. The link wraps the picture and name; the caption line (with its i) sits outside it."""
    return (f'<figure class="tile {cls}"><a class="hit" href="{href}">{pic}{extra}<div class="name">{name}</div></a>'
            f'<div class="capline">{cap}</div></figure>')


def event_tile(e, extra_cls=''):
    rel = img_rel(e); cat = CAT_OF[e['type']]; name = short_name(e)
    if rel:
        pic = f'<img src="{REL}/{rel}" alt="{esc(credits[rel]["title"])}" loading="lazy">'
    else:
        pic = (f'<div class="typo">{glyph(cat, 22, 1.6)}<div><div class="t">{esc(name)}</div>'
               f'<div class="d" style="margin-top:8px">{esc(TYPE_LABEL[e["type"]])} · {day(e["observed_at"])}</div></div></div>')
    return tile('event.html', pic, f'{glyph(cat)}<b>{esc(name)}</b>', f'<span class="cap">{esc(flag(e, rel))}</span>', cls=extra_cls)


# ---------------------------------------------------------------- sky geometry
def to_gal(ra, dec):
    ra, dec = math.radians(ra), math.radians(dec)
    ra_gp, dec_gp, l_ncp = math.radians(192.85948), math.radians(27.12825), math.radians(122.93192)
    sb = math.sin(dec) * math.sin(dec_gp) + math.cos(dec) * math.cos(dec_gp) * math.cos(ra - ra_gp)
    b = math.asin(sb)
    y = math.cos(dec) * math.sin(ra - ra_gp)
    x = math.sin(dec) * math.cos(dec_gp) - math.cos(dec) * math.sin(dec_gp) * math.cos(ra - ra_gp)
    l = l_ncp - math.atan2(y, x)
    return math.degrees(l) % 360, math.degrees(b)


def pano_xy(ra, dec, W, H):
    l, b = to_gal(ra, dec)
    return ((180 - l) % 360) / 360 * W, (90 - b) / 180 * H


CL = json.load(open(f'{HERE}/data/const.lines.json'))
CN = json.load(open(f'{HERE}/data/const.json'))
CB = json.load(open(f'{HERE}/data/const.bounds.json'))


def constellation_of(ra, dec):
    """IAU constellation containing (ra, dec): ray casting on each boundary ring, unwrapped in RA."""
    def unwrap(ring):
        out = [list(ring[0])]
        for x, y in ring[1:]:
            px = out[-1][0]
            x = px + ((x - px + 540) % 360 - 180)
            out.append([x, y])
        return out

    def inside(ring, x, y):
        ins = False; n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % n]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                ins = not ins
        return ins

    for f in CB['features']:
        for poly in f['geometry']['coordinates']:
            ring = unwrap(poly if isinstance(poly[0][0], (int, float)) else poly[0])
            if any(inside(ring, ra + k, dec) for k in (-720, -360, 0, 360, 720)):
                return next((g['properties']['name'] for g in CN['features'] if g['id'] == f['id']), f['id'])
    if abs(dec) > 80:
        return 'Ursa Minor' if dec > 0 else 'Octans'
    return None


def lines_svg(W, H, x0=0, y0=0, w=None, h=None, stroke=1.0, opacity=0.28, names=True, name_size=11, rank_max=2):
    """Constellation lines and names over the galactic panorama. (x0, y0, w, h) is a window in panorama pixels."""
    w = w or W; h = h or H
    out = []
    def wx(x):
        return (x - x0 + W / 2) % W - W / 2 if w < W else x - x0
    for f in CL['features']:
        for line in f['geometry']['coordinates']:
            pts = [pano_xy(lo % 360, la, W, H) for lo, la in line]
            seg = []
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                if abs(xb - xa) > W / 2:
                    continue
                ax, bx = wx(xa), wx(xb)
                if abs(bx - ax) > W / 2:  # the pair straddles the window's own seam
                    continue
                if max(ax, bx) < -50 or min(ax, bx) > w + 50 or max(ya, yb) - y0 < -50 or min(ya, yb) - y0 > h + 50:
                    continue
                seg.append(f'M{ax:.1f} {ya-y0:.1f}L{bx:.1f} {yb-y0:.1f}')
            if seg:
                out.append(''.join(seg))
    s = [f'<path d="{"".join(out)}" fill="none" stroke="#DCE4FF" stroke-opacity="{opacity}" stroke-width="{stroke}" vector-effect="non-scaling-stroke"/>']
    if names:
        for f in CN['features']:
            if int(f['properties'].get('rank', 3)) > rank_max:
                continue
            lo, la = f['geometry']['coordinates']
            x, y = pano_xy(lo % 360, la, W, H)
            x = wx(x); y -= y0
            if 0 <= x <= w and 0 <= y <= h:
                s.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" fill="#DCE4FF" fill-opacity="0.55" '
                         f'style="font:400 {name_size}px var(--font-mono);letter-spacing:.06em;text-transform:uppercase">{esc(f["properties"]["name"])}</text>')
    return ''.join(s)


def where_crop(e, big_pano, span_l=56, span_b=34):
    """Crop of the ESO panorama around the event, saved to public/images/sky/where/. Returns rel, svg overlay."""
    loc = e['location']
    im = Image.open(big_pano); W, H = im.size
    cx, cy = pano_xy(loc['ra_deg'], loc['dec_deg'], W, H)
    w = round(span_l / 360 * W); h = round(span_b / 180 * H)
    x0 = round(cx - w / 2); y0 = max(0, min(H - h, round(cy - h / 2)))
    strip = Image.new('RGB', (w, h))
    for dx in range(-W, 2 * W, W):  # handle wrap at l = 180
        box = (x0 - dx, y0, x0 - dx + w, y0 + h)
        if box[2] <= 0 or box[0] >= W:
            continue
        a = max(0, box[0]); b = min(W, box[2])
        strip.paste(im.crop((a, y0, b, y0 + h)), (a - box[0], 0))
    sid = e['id'].replace(':', '-')
    rel = f'sky/where/{sid}.jpg'
    os.makedirs(f'{IMG}/sky/where', exist_ok=True)
    strip.save(f'{IMG}/{rel}', 'JPEG', quality=86, optimize=True, progressive=True)
    credits[rel] = {'url': 'https://www.eso.org/public/images/eso0932a/', 'title': f'The Milky Way panorama, cropped around {e["title"]}',
                    'credit': 'ESO/S. Brunier', 'licence': 'CC BY 4.0', 'source': 'ESO', 'width': w, 'height': h,
                    'note': 'Crop of eso0932a (galactic coordinates, equirectangular); constellation lines from d3-celestial (BSD-3-Clause)'}
    mx, my = cx - x0, cy - y0
    svg = (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" style="position:absolute;inset:0;width:100%;height:100%">'
           + lines_svg(W, H, x0, y0, w, h, 1.0, 0.35, True, 15, 3)
           + f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="16" fill="none" stroke="#000" stroke-width="5"/>'
           + f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="16" fill="none" stroke="var(--cat-transient)" stroke-width="2.4"/></svg>')
    return rel, svg


# ---------------------------------------------------------------- data graphics
def sparkline(cid, w=320, h=56):
    c = json.load(open(f'{WEB}/public/data/finder/c/{cid}.json'))['candidate']
    P = c['period_d']; pts = [(p * P * 24, f) for p, f in zip(c['folded']['phase'], c['folded']['flux']) if abs(p * P * 24) <= 8]
    b = {}
    for x, f in pts:
        b.setdefault(round(x * 2) / 2, []).append(f)
    med = [(k, statistics.median(v)) for k, v in sorted(b.items())]
    lo = min(v for _, v in med); hi = max(v for _, v in med); pad = (hi - lo) * 0.25 or 1e-4
    X = lambda x: (x + 8) / 16 * w
    Y = lambda f: 4 + (hi + pad - f) / (hi - lo + 2 * pad) * (h - 8)
    d = 'M' + ' L'.join(f'{X(x):.1f} {Y(f):.1f}' for x, f in med)
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" style="width:100%;height:{h}px;display:block" aria-hidden="true">'
            f'<path d="{d}" fill="none" stroke="#F4F4F5" stroke-width="1.25" vector-effect="non-scaling-stroke"/></svg>')


def render_pixels_png():
    """WASP-18's real TESS pixels (sector 104), drawn as a picture."""
    rel = 'data/wasp18-tess-pixels-s0104.png'
    if rel in credits and os.path.exists(f'{IMG}/{rel}'):
        return rel
    d = json.load(open(f'{WEB}/components/finder/data/pixels-wasp18-s0104.json'))
    g = d['out_of_transit']; n = len(g); cs = 96
    vals = [v for r in g for v in r if v is not None]
    lo, hi = math.log10(max(min(vals), 1)), math.log10(max(vals))
    im = Image.new('RGB', (n * cs, n * cs))
    px = im.load()
    for y, row in enumerate(g):
        for x, v in enumerate(row):
            k = (math.log10(max(v or 1, 1)) - lo) / (hi - lo); gg = round(8 + 247 * max(0, min(1, k)) ** 1.3)
            for yy in range(y * cs, y * cs + cs):
                for xx in range(x * cs, x * cs + cs):
                    px[xx, yy] = (gg, gg, gg)
    os.makedirs(f'{IMG}/data', exist_ok=True)
    im.save(f'{IMG}/{rel}', optimize=True)
    credits[rel] = {'url': 'https://archive.stsci.edu/missions-and-data/tess', 'title': 'WASP-18 in TESS pixels, sector 104 (between dips)',
                    'credit': 'NASA TESS mission, via MAST; rendered by Planet Hunter', 'licence': 'Public domain (NASA data)',
                    'source': 'Planet Hunter render of TESS data', 'width': im.width, 'height': im.height}
    return rel


# ---------------------------------------------------------------- pages
def home():
    ev = week()
    pick_ids = ['donki:2026-09-19T17:57:00-FLR-001', 'tns:2026acna', 'tns:2026abvs', 'ztf:ZTF22abegjtx',
                'donki:2026-09-24T14:45:00-CME-001', 'tns:2026aajs', 'ztf:ZTF26abkjlpd', 'tns:2026acow', 'ztf:ZTF26abnuiar']
    byid = {e['id']: e for e in events_all}
    tiles = ''.join(event_tile(byid[i], 'big' if k == 0 else '') for k, i in enumerate(pick_ids))
    cands = cand_index['candidates'][:6]
    ctiles = ''.join(tile('finder-id.html', f'<img src="{REL}/stars/tic{c["tic"]}.jpg" alt="Survey image of the sky around TIC {c["tic"]}" loading="lazy">',
                          f'<b>TIC {c["tic"]}</b>', f'<span class="cap">{c["period_d"]:.2f} d · candidate</span>',
                          extra=f'<div class="spark">{sparkline(c["id"])}</div>') for c in cands)
    lab = [('Star thermometer', 'feature/heic0715a.jpg'), ('Hear a star', render_pixels_png()),
           ('Hubble diagram', 'feature/heic0406a.jpg'), ('Chemical fingerprints', 'events/donki-2026-09-19T17-57-00-FLR-001.jpg')]
    ltiles = ''.join(tile('lab.html', f'<img src="{REL}/{r}" alt="{esc(credits[r]["title"])}" loading="lazy">', f'<b>{n}</b>',
                          f'<span class="cap">{esc(src_short(r))}</span>{info(r)}') for n, r in lab)
    famous = [('WASP-18', 100100827), ('WASP-121', 22529346), ('WASP-43', 36734222), ('TOI-700', 150428135)]
    ftiles = ''.join(tile('#', f'<img src="{REL}/stars/tic{t}.jpg" alt="Survey image of {n}" loading="lazy">', f'<b>{n}</b>',
                          f'<span class="cap">{src_short(f"stars/tic{t}.jpg")} · archive</span>{info(f"stars/tic{t}.jpg")}') for n, t in famous)
    hero = 'sky/eso0733a.jpg'
    body = f'''{topbar(None, over=True)}
<main>
  <section class="hero" aria-labelledby="h">
    <img src="{REL}/{hero}" alt="{esc(credits[hero]['title'])}: the Milky Way's centre over Paranal">
    <div class="wrap hero-copy"><h1 id="h" class="display">The sky this week,<br>in real pictures.</h1></div>
  </section>
  <div class="wrap"><div class="capline hero-cap"><span class="cap">ESO/Y. Beletsky · Paranal Observatory</span>{info(hero)}</div></div>

  <section class="wrap sec" aria-labelledby="w">
    <div class="shead"><div><h2 id="w" class="h2">This week</h2><p class="line"><span class="num">{len(ev)}</span> events in 7 days.</p></div><a class="btn btn-quiet" href="events.html">All events →</a></div>
    <div class="bento">{tiles}</div>
  </section>

  <section class="wrap sec" aria-labelledby="c">
    <div class="shead"><div><h2 id="c" class="h2">Candidates</h2><p class="line">Dips in starlight, waiting for your eye.</p></div><a class="btn btn-quiet" href="finder.html">All 14 →</a></div>
    <div class="row6">{ctiles}</div>
  </section>

  <section class="wrap sec" aria-labelledby="l">
    <div class="shead"><div><h2 id="l" class="h2">Lab</h2><p class="line">Experiments on real stars.</p></div><a class="btn btn-quiet" href="lab.html">Open the lab →</a></div>
    <div class="row4 tall">{ltiles}</div>
  </section>

  <section class="wrap sec" aria-labelledby="f">
    <div class="shead"><div><h2 id="f" class="h2">Famous stars</h2></div></div>
    <div class="row4">{ftiles}</div>
  </section>

  <section class="wrap sec end" aria-label="Honesty">
    <details class="drawer"><summary>How we stay honest<span class="aside">3 rules</span></summary><div class="body">
      <p>Every picture is real and credited; tap <b>i</b> on any picture for its source and licence. Survey pictures marked archive were taken years before the event.</p>
      <p style="margin-top:12px">When a computer sorted something, the caption says "guess" with how sure it was.</p>
      <p style="margin-top:12px">A dip in a star's light is a planet candidate until astronomers confirm it.</p></div></details>
    <details class="drawer"><summary>Data and picture credits<span class="aside">{len(credits)} pictures</span></summary><div class="body">NASA, ESA/Webb, ESA/Hubble, ESO, NOIRLab, SDO via Helioviewer, and survey cutouts cut with CDS hips2fits. The full list with licences is in credits.json.</div></details>
  </section>
</main>'''
    css = '''
.hero{position:relative;height:min(100vh,920px);min-height:640px;overflow:hidden;background:#000}
.hero img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:50% 60%}
.hero-copy{position:absolute;left:0;right:0;bottom:96px}
.hero-cap{margin-top:12px}
.sec{padding-top:var(--section)}
.sec.end{padding-bottom:var(--section)}
.bento{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--tile-gap-y) var(--gap)}
.bento .big{grid-column:span 2;grid-row:span 2;display:flex;flex-direction:column}
.bento .big img{flex:1;aspect-ratio:auto;min-height:0}
.row6{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:var(--tile-gap-y) var(--gap)}
.row4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--tile-gap-y) var(--gap)}
.row4.tall img{aspect-ratio:3/4}
.spark{margin-top:12px;border-top:1px solid var(--line-faint);padding-top:8px}
@media (max-width:1023px){.row6{grid-template-columns:repeat(3,minmax(0,1fr))}.bento{grid-template-columns:repeat(2,minmax(0,1fr))}.bento .tile:nth-child(n+6){display:none}}
@media (max-width:639px){.hero{height:88vh;min-height:560px}.hero img{object-position:62% 60%}.hero-copy{bottom:48px}
.row4{grid-template-columns:repeat(2,minmax(0,1fr))}.row6{grid-template-columns:repeat(2,minmax(0,1fr))}.row6 .tile:nth-child(n+5){display:none}
.bento .big{grid-column:span 2;grid-row:auto}.bento .big img{aspect-ratio:1}}
'''
    return page('Planet Hunter', body, css)


def events_page():
    ev = week()
    counts = {c: sum(1 for e in ev if CAT_OF[e['type']] == c) for c in CATEGORIES}
    chips = ''.join(f'<button class="chip" aria-pressed="{"true" if counts[c] else "false"}">{glyph(c)}{CHIP[c]}<span class="c">{counts[c]}</span></button>' for c in CATEGORIES)
    groups = {}
    for e in ev:
        groups.setdefault(e['observed_at'][:10], []).append(e)
    rows = ''
    for d, es in groups.items():
        dt = datetime.fromisoformat(d)
        rel = (NOW.date() - dt.date()).days
        lab = 'Today' if rel == 0 else 'Yesterday' if rel == 1 else f'{dt.day} {MON[dt.month-1]}'
        rows += (f'<section class="day"><div class="dayhead"><span class="label">{lab}</span><span class="label">{len(es)}</span></div>'
                 f'<div class="grid">{"".join(event_tile(e) for e in es)}</div></section>')
    body = f'''{topbar('Events')}
<main class="wrap">
  <div class="head"><h1 class="h1">Events</h1><div class="headend"><span class="tag">Demo data</span>
    <div class="seg" role="radiogroup" aria-label="View"><button role="radio" aria-checked="true">Pictures</button><button role="radio" aria-checked="false" onclick="location.href='sky.html'">Sky</button></div></div></div>
  <div class="fbar" role="toolbar" aria-label="Filters">
    <div class="seg" role="radiogroup" aria-label="Time"><button role="radio" aria-checked="false">24 h</button><button role="radio" aria-checked="true">7 d</button><button role="radio" aria-checked="false">30 d</button></div>
    {chips}<button class="chip"><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" stroke-width="1.3"/><circle cx="5" cy="4" r="1.6" fill="#000" stroke="currentColor" stroke-width="1.3"/><circle cx="11" cy="8" r="1.6" fill="#000" stroke="currentColor" stroke-width="1.3"/><circle cx="7" cy="12" r="1.6" fill="#000" stroke="currentColor" stroke-width="1.3"/></svg>More</button>
  </div>
  {rows}
</main>'''
    css = '''
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding-top:64px;margin-bottom:32px;flex-wrap:wrap}
.headend{display:flex;align-items:center;gap:16px}
.fbar{position:sticky;top:var(--topbar-h);z-index:5;background:#000;padding:12px 0;margin-bottom:32px}
.day{padding:40px 0 24px}
.dayhead{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding-top:12px;margin-bottom:24px}
.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:var(--tile-gap-y) var(--gap)}
main{padding-bottom:var(--section)}
@media (max-width:1279px){.grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media (max-width:1023px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:639px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.head{padding-top:40px}.typo{padding:14px}.typo .t{font-size:16px;line-height:20px}}
'''
    return page('Events', body, css)


def event_page(big_pano):
    e = next(x for x in events_all if x['id'] == 'tns:2026abvs')
    rel = img_rel(e); loc = e['location']
    wrel, overlay = where_crop(e, big_pano)
    con = constellation_of(loc['ra_deg'], loc['dec_deg'])
    ra_h = loc['ra_deg'] / 15; rh = int(ra_h); rm = int((ra_h - rh) * 60)
    dd = abs(loc['dec_deg']); dg = int(dd); dm = int((dd - dg) * 60)
    raw = e.get('raw') or {}
    body = f'''{topbar('Events')}
<main class="wrap">
  <a class="btn btn-quiet crumb" href="events.html">← Events</a>
  <div class="split">
    <figure class="lead"><img src="{REL}/{rel}" alt="{esc(credits[rel]['title'])}">
      <div class="capline"><span class="cap">{esc(src_short(rel))} · archive, years before the event</span>{info(rel, '<div style="margin-top:8px">The supernova itself is not in this picture; its host galaxy is.</div>')}</div></figure>
    <div class="side">
      <div class="kind">{glyph('transients', 12)}<span class="label">Supernova · type IIn</span></div>
      <h1 class="h1">SN 2026abvs</h1>
      <p class="cap" style="margin-top:12px">25 Sep 2026, 11:49 UTC · TNS · official report</p>
      <dl class="facts">
        <div><dt class="label">Reported</dt><dd>4 h ago</dd></div>
        <div><dt class="label">In</dt><dd>{esc(con or '')}</dd></div>
        <div><dt class="label">Position</dt><dd class="num">{rh:02d}h{rm:02d}m {"+" if loc["dec_deg"] >= 0 else "−"}{dg:02d}°{dm:02d}′</dd></div>
      </dl>
      <figure class="where"><div class="where-pic"><img src="{REL}/{wrel}" alt="Where it is: the Milky Way panorama around {esc(con or '')}">{overlay}</div>
        <div class="capline"><span class="cap">Where it is · ESO/S. Brunier</span>{info(wrel)}</div></figure>
      <div class="actions"><a class="btn btn-secondary" href="sky.html">Open in sky</a><a class="btn btn-quiet" href="{esc(e['source_url'] or '#')}">TNS report ↗</a></div>
    </div>
  </div>
  <section class="more">
    <details class="drawer"><summary>How we know<span class="aside">TNS report</span></summary><div class="body">{esc(e['summary'] or '')}</div></details>
    <details class="drawer"><summary>About the picture<span class="aside">Archive</span></summary><div class="body">{esc(credits[rel]['title'])}. {esc(credits[rel]['credit'])}.</div></details>
  </section>
</main>'''
    css = '''
main{padding-top:40px;padding-bottom:var(--section)}
.split{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,4fr);gap:96px;margin-top:32px;align-items:start}
.lead img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:var(--r-tag)}
.side{position:sticky;top:calc(var(--topbar-h) + 32px)}
.kind{display:flex;align-items:center;gap:10px;margin-bottom:16px}
.facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin:40px 0 0;border-top:1px solid var(--line)}
.facts div{padding:14px 0}.facts dd{margin:6px 0 0;font-size:15px}
.where{margin-top:40px}
.where-pic{position:relative;aspect-ratio:56/34;overflow:hidden;border-radius:var(--r-tag);background:#000}
.where-pic img{width:100%;height:100%;object-fit:cover}
.actions{display:flex;align-items:center;gap:20px;margin-top:32px}
.more{margin-top:var(--section-app)}
@media (max-width:1023px){.split{grid-template-columns:1fr;gap:48px}.side{position:static}}
'''
    return page('SN 2026abvs', body, css)


def sky_page():
    rel = 'sky/eso0932a.jpg'; W, H = 4000, 2000
    ev = [e for e in week() if (e.get('location') or {}).get('frame') == 'sky']
    marks = ''
    for e in ev:
        x, y = pano_xy(e['location']['ra_deg'], e['location']['dec_deg'], W, H)
        c = CAT_OF[e['type']]
        marks += f'<g transform="translate({x:.0f} {y:.0f}) scale(3.2) translate(-5 -5)">{glyph(c).replace("<svg", "<svg overflow=\"visible\"")}</g>'
    body = f'''{topbar('Sky')}
<main>
  <div class="wrap skyhead"><h1 class="h1">Sky</h1><div class="seg" role="radiogroup" aria-label="View"><button role="radio" aria-checked="false" onclick="location.href='events.html'">Pictures</button><button role="radio" aria-checked="true">Sky</button></div></div>
  <div class="pano" tabindex="0" aria-label="The whole sky, scroll sideways">
    <div class="pano-in"><img src="{REL}/{rel}" alt="The Milky Way panorama: the whole sky in one photograph">
      <svg viewBox="0 0 {W} {H}" style="position:absolute;inset:0;width:100%;height:100%">{lines_svg(W, H, stroke=1, opacity=0.22, names=True, name_size=26, rank_max=1)}{marks}</svg></div>
  </div>
  <div class="wrap"><div class="capline"><span class="cap">ESO/S. Brunier · the whole sky · {len(ev)} events</span>{info(rel, '<div style="margin-top:8px">Constellation lines and names: d3-celestial (BSD-3-Clause). The galactic plane runs across the middle.</div>')}</div></div>
</main>'''
    css = '''
.skyhead{display:flex;align-items:flex-end;justify-content:space-between;padding-top:48px;margin-bottom:32px}
.pano{overflow-x:auto;scrollbar-width:none}.pano::-webkit-scrollbar{display:none}
.pano-in{position:relative;width:100%;aspect-ratio:2/1}
.pano-in img{width:100%;height:100%;object-fit:cover}
main{padding-bottom:var(--section-app)}
@media (max-width:639px){.pano-in{width:1100px}.pano{scroll-snap-type:x mandatory}}
'''
    return page('Sky', body, css)


def lab_page():
    items = [('Star thermometer', 'feature/heic0715a.jpg', 'A star’s colour is its temperature.'),
             ('Hear a star', render_pixels_png(), 'Its light, as sound.'),
             ('Hubble diagram', 'feature/heic0406a.jpg', 'Rebuild the expanding universe.'),
             ('Chemical fingerprints', 'events/donki-2026-09-19T17-57-00-FLR-001.jpg', 'Elements by their light.')]
    tiles = ''.join(tile('#', f'<img src="{REL}/{r}" alt="{esc(credits[r]["title"])}" loading="lazy">', f'<b>{n}</b>',
                         f'<span class="cap">{esc(src_short(r))}</span>{info(r)}', cls='exp') for n, r, _ in items)
    famous = [('WASP-18', 100100827), ('WASP-121', 22529346), ('WASP-43', 36734222), ('TOI-700', 150428135)]
    stars = ''.join(tile('#', f'<img src="{REL}/stars/tic{t}.jpg" alt="Survey image of {n}" loading="lazy">', f'<b>{n}</b>',
                         f'<span class="cap">Star lab · archive photo</span>{info(f"stars/tic{t}.jpg")}') for n, t in famous)
    hero = 'feature/weic2205a.jpg'
    body = f'''{topbar('Lab', over=True)}
<main>
  <section class="hero"><img src="{REL}/{hero}" alt="{esc(credits[hero]['title'])}"><div class="wrap hero-copy"><h1 class="display">Lab</h1><p class="line" style="color:var(--ink);margin-top:16px">Experiments on real stars.</p></div></section>
  <div class="wrap"><div class="capline"><span class="cap">NASA · ESA · CSA · STScI · Webb, Carina Nebula</span>{info(hero)}</div></div>
  <section class="wrap sec"><div class="grid2">{tiles}</div></section>
  <section class="wrap sec"><div class="shead"><h2 class="h2">Star labs</h2><a class="btn btn-quiet" href="#">Find a star →</a></div><div class="row4">{stars}</div></section>
  <section class="wrap sec end"><details class="drawer"><summary>What the lab is<span class="aside">About</span></summary><div class="body">Small experiments that use real measurements of real stars. Each one says which numbers are measured and which are estimates.</div></details></section>
</main>'''
    css = '''
.hero{position:relative;height:72vh;min-height:520px;overflow:hidden}.hero img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:50% 70%}
.hero-copy{position:absolute;left:0;right:0;bottom:80px}
.sec{padding-top:var(--section)}.sec.end{padding-bottom:var(--section)}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:64px var(--gap)}
.grid2 img{aspect-ratio:4/3}
.row4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--tile-gap-y) var(--gap)}
.exp .name{font-size:18px;margin-top:16px}
@media (max-width:639px){.grid2{grid-template-columns:1fr;gap:40px}.row4{grid-template-columns:repeat(2,minmax(0,1fr))}.hero{height:64vh}}
'''
    return page('Lab', body, css)


def finder_page():
    cands = cand_index['candidates']
    tiles = ''.join(tile('finder-id.html', f'<img src="{REL}/stars/tic{c["tic"]}.jpg" alt="Survey image around TIC {c["tic"]}" loading="lazy">',
                         f'<b>{esc(c.get("name") or "TIC " + str(c["tic"]))}</b>',
                         f'<span class="cap">{c["period_d"]:.2f} d · {c["radius_rjup"]*11.21:.1f} R⊕ · priority {c["score"]:.2f}</span>',
                         extra=f'<div class="spark">{sparkline(c["id"])}</div>') for c in cands)
    body = f'''{topbar('Finder')}
<main class="wrap">
  <div class="head"><div><h1 class="h1">Candidates</h1><p class="line" style="margin-top:12px">Dips in starlight, waiting for your eye.</p></div>
    <div class="headend"><span class="tag">Demo data</span></div></div>
  <div class="bar"><span class="cap"><span class="num">48,213</span> stars searched → <span class="num">14</span> to review</span>
    <div class="tools"><button class="chip">Priority ▾</button><button class="chip">Filter</button></div></div>
  <div class="grid">{tiles}</div>
  <section class="sec"><details class="drawer"><summary>What the search can find<span class="aside">Sensitivity</span></summary><div class="body">Which planet sizes and orbits the search recovers, from planets we hid in real light curves.</div></details>
  <details class="drawer"><summary>What a candidate is<span class="aside">About</span></summary><div class="body">A repeating dip that passed our checks and is on none of the lists we compared. None is a planet yet.</div></details></section>
</main>'''
    css = '''
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding-top:64px;margin-bottom:48px;flex-wrap:wrap}
.bar{display:flex;align-items:center;justify-content:space-between;gap:16px;border-top:1px solid var(--line);padding-top:16px;margin-bottom:40px;flex-wrap:wrap}
.tools{display:flex;gap:8px}
.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:56px var(--gap)}
.spark{margin-top:12px;border-top:1px solid var(--line-faint);padding-top:8px}
.sec{padding-top:var(--section-app);padding-bottom:var(--section)}
@media (max-width:1279px){.grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media (max-width:639px){.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:36px var(--gap)}.head{padding-top:40px}}
'''
    return page('Finder', body, css)


def finder_id_page():
    sys.path.insert(0, os.path.dirname(HERE) + '/mocks')
    c = json.load(open(f'{WEB}/public/data/finder/c/tic219345170-01.json'))
    cc = c['candidate']
    import importlib.util
    spec = importlib.util.spec_from_file_location('gf', os.path.join(HERE, 'charts.py'))
    gf = importlib.util.module_from_spec(spec); spec.loader.exec_module(gf)
    fold = gf.fold(640, 400); foldn = gf.fold(330, 260); full = gf.full(1312, 260, 10, 2400); fulln = gf.full(350, 220, 20, 900)
    oot = gf.heat(c['pixels']['images']['out_of_transit'], False); dif = gf.heat(c['pixels']['images']['difference'], True)
    checks = gf.checks()
    body = f'''{topbar('Finder')}
<main class="wrap">
  <a class="btn btn-quiet crumb" href="finder.html">← Candidates</a>
  <div class="lead">
    <figure><img src="{REL}/stars/tic219345170.jpg" alt="Survey image of the sky around TIC 219345170">
      <div class="capline"><span class="cap">DESI Legacy Surveys · archive · the star is centred</span>{info('stars/tic219345170.jpg')}</div></figure>
    <figure class="chart"><div class="only-wide">{fold}</div><div class="only-narrow">{foldn}</div><div class="capline"><span class="cap">13 dips stacked · TESS sectors 81, 82 · demo</span></div></figure>
  </div>
  <div class="split">
    <div>
      <div class="title"><h1 class="h1">TIC 219345170</h1><span class="tag">Demo data</span></div>
      <p class="line" style="margin-top:12px">A dip every 3.81 days. A candidate, not a planet.</p>
      <dl class="facts">
        <div><dt class="label">Period</dt><dd><span class="num">3.81</span><span class="unit">days</span></dd></div>
        <div><dt class="label">Size</dt><dd><span class="num">4.4</span><span class="unit">× Earth</span></dd></div>
        <div><dt class="label">Checks</dt><dd><span class="num">6</span><span class="unit">of 6</span></dd></div>
        <div><dt class="label">Priority</dt><dd><span class="num">0.90</span></dd></div>
      </dl>
    </div>
    <aside class="vote" aria-labelledby="v"><h2 id="v" style="font-size:18px">Does it look like a planet?</h2>
      <div class="opts"><button class="opt">Looks like a planet</button><button class="opt">Probably not</button><button class="opt">Not sure</button></div>
      <p class="cap" style="margin-top:16px">Votes show after you vote</p></aside>
  </div>
  <section class="block"><div class="only-wide">{full}</div><div class="only-narrow">{fulln}</div>
    <div class="capline"><span class="cap">The whole light curve · ticks mark each predicted dip · demo</span></div></section>
  <section class="block pix"><figure>{oot}<div class="capline"><span class="cap">Between dips</span></div></figure>
    <figure>{dif}<div class="capline"><span class="cap">Light that went missing</span></div></figure>
    <div class="pixnote"><div class="label">On target</div><div class="big num">95<span class="unit" style="margin-left:0">%</span></div><div class="cap" style="margin-top:6px">From the pixel check</div></div></section>
  <section class="block">
    <details class="drawer"><summary>Checks<span class="aside">6 of 6 passed</span></summary><div class="body" style="max-width:none"><table class="checks">{checks}</table></div></details>
    <details class="drawer"><summary>Pixel check<span class="aside">On target</span></summary><div class="body">TESS pixels are 21″ across, so light from neighbours can mix. The missing light is centred on the target (1.4″ off, 0.9σ). Demo: these pixels are WASP-18's, sector 104.</div></details>
    <details class="drawer"><summary>Known lists<span class="aside">On none</span></summary><div class="body">Not on the NASA Exoplanet Archive, TOI, CTOI or TESS EB lists in the copies we checked.</div></details>
    <details class="drawer"><summary>Priority<span class="aside">0.90</span></summary><div class="body">A machine ranking from signal, shape, checks and pixels. It orders the list; it is not the chance this is a planet.</div></details>
    <details class="drawer"><summary>What a candidate is<span class="aside">About</span></summary><div class="body">A repeating dip that passed our checks and is on none of the lists. Confirmation needs sharper images and the star's wobble, and takes months to years.</div></details>
  </section>
</main>'''
    css = '''
main{padding-top:40px;padding-bottom:var(--section)}
.lead{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--gap);margin-top:32px;align-items:start}
.lead img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:var(--r-tag)}
.chart{background:var(--well);border-radius:var(--r-tag);padding:24px 24px 8px}
.chart svg{width:100%;height:auto;display:block;overflow:visible}
svg text{font:400 11px var(--font-mono);fill:var(--ink-muted)} svg text.t{font-family:var(--font-sans);font-size:12px;fill:var(--ink-secondary)}
.split{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:96px;margin-top:64px;align-items:start}
.title{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:40px 0 0;border-top:1px solid var(--line)}
.facts div{padding:16px 16px 0 0}.facts dd{margin:8px 0 0;font:400 24px/28px var(--font-mono);letter-spacing:-.02em}.facts .unit{font-size:14px}
.vote{border:1px solid var(--line);border-radius:var(--r-float);padding:24px;background:var(--raised)}
.opts{display:grid;gap:8px;margin-top:16px}.opt{height:44px;border:1px solid var(--line-strong);border-radius:var(--r-control);text-align:left;padding:0 14px;font-size:14px}
.block{margin-top:var(--section-app)}
.block svg{width:100%;height:auto;display:block;overflow:visible}
.pix{display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--gap);align-items:start}
.pixnote{align-self:end}.pixnote .big{font-size:48px;line-height:52px;letter-spacing:-.03em;margin-top:8px}
.checks{width:100%;border-collapse:collapse}.checks td{padding:10px 16px 10px 0;border-top:1px solid var(--line-faint);vertical-align:top}.checks .val{text-align:right;white-space:nowrap}
.only-narrow{display:none}
@media (max-width:1023px){.split{grid-template-columns:1fr;gap:48px}}
@media (max-width:639px){.lead{grid-template-columns:1fr}.facts{grid-template-columns:repeat(2,minmax(0,1fr))}.pix{grid-template-columns:1fr 1fr}.pixnote{grid-column:1/-1}
.only-wide{display:none}.only-narrow{display:block}.checks .why{display:none}.chart{padding:16px 12px 4px}}
'''
    return page('TIC 219345170', body, css)


if __name__ == '__main__':
    big = sys.argv[1] if len(sys.argv) > 1 else None
    out = {'home': home(), 'events': events_page(), 'sky': sky_page(), 'lab': lab_page(), 'finder': finder_page(), 'finder-id': finder_id_page()}
    if big:
        out['event'] = event_page(big)
    for k, v in out.items():
        open(f'{HERE}/{k}.html', 'w').write(v)
    json.dump(credits, open(f'{IMG}/credits.json', 'w'), indent=1, ensure_ascii=False)
    print('built', ', '.join(out), '|', len(credits), 'credited pictures')
