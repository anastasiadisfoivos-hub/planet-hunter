"""Fetch the real pictures (python3 docs/polish/mocks-v2/fetch_images.py [features|stars|events]) for the POLISH v2 mocks into web/public/images/ and write credits.json.

Every entry records the page URL, title, credit and licence. Nothing here is generated: photographs and
instrument images from NASA, ESA/Webb, ESA/Hubble, ESO, NOIRLab, SDO (via Helioviewer) and survey cutouts
cut with CDS hips2fits.
"""
import io, json, os, subprocess, sys, urllib.parse
from PIL import Image

WEB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))
OUT = f'{WEB}/public/images'
os.makedirs(OUT, exist_ok=True)
CREDITS_PATH = f'{OUT}/credits.json'
credits = json.load(open(CREDITS_PATH)) if os.path.exists(CREDITS_PATH) else {}


def get(url, timeout=120):
    r = subprocess.run(['curl', '-sSL', '--fail', '--max-time', str(timeout), url], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f'{url}: {r.stderr.decode()[:200]}')
    return r.stdout


def save(rel, data, max_w=2400, q=82):
    im = Image.open(io.BytesIO(data)).convert('RGB')
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    path = f'{OUT}/{rel}'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, 'JPEG', quality=q, optimize=True, progressive=True)
    return im.size


def add(rel, url, title, credit, licence, source, size, **extra):
    credits[rel] = {'url': url, 'title': title, 'credit': credit, 'licence': licence, 'source': source,
                    'width': size[0], 'height': size[1], **extra}


CC = 'CC BY 4.0'
FEATURE = [
    # rel, file url, page url, title, credit, licence, source, max_w
    ('sky/eso0733a.jpg', 'https://cdn.eso.org/images/large/eso0733a.jpg', 'https://www.eso.org/public/images/eso0733a/',
     'The planet, the galaxy and the laser', 'ESO/Y. Beletsky', CC, 'ESO', 2400),
    ('sky/eso0932a.jpg', 'https://cdn.eso.org/images/large/eso0932a.jpg', 'https://www.eso.org/public/images/eso0932a/',
     'The Milky Way panorama', 'ESO/S. Brunier', CC, 'ESO', 4000),
    # NOIRLab's storage refuses non-browser requests: this one was saved from the image page in a browser.
    ('feature/noirlab2521a.jpg', 'https://storage.noirlab.edu/media/archives/images/wallpaper5/noirlab2521a.jpg', 'https://noirlab.edu/public/images/noirlab2521a/',
     'The Cosmic Treasure Chest', 'NSF–DOE Vera C. Rubin Observatory/NOIRLab/SLAC/AURA', CC, 'NOIRLab', 2400),
    ('feature/weic2205a.jpg', 'https://cdn.esawebb.org/archives/images/large/weic2205a.jpg', 'https://esawebb.org/images/weic2205a/',
     'Cosmic Cliffs in the Carina Nebula (NIRCam image)', 'NASA, ESA, CSA, and STScI', CC, 'ESA/Webb', 2400),
    ('feature/heic0406a.jpg', 'https://cdn.esahubble.org/archives/images/large/heic0406a.jpg', 'https://esahubble.org/images/heic0406a/',
     'Hubble sees galaxies galore (Hubble Ultra Deep Field)', 'NASA, ESA, and S. Beckwith (STScI) and the HUDF Team', CC, 'ESA/Hubble', 2400),
    ('feature/heic0715a.jpg', 'https://cdn.esahubble.org/archives/images/large/heic0715a.jpg', 'https://esahubble.org/images/heic0715a/',
     'Extreme star cluster bursts into life (NGC 3603)', 'NASA, ESA and the Hubble Heritage (STScI/AURA)-ESA/Hubble Collaboration', CC, 'ESA/Hubble', 2400),
    ('feature/PIA11984.jpg', 'https://images-assets.nasa.gov/image/PIA11984/PIA11984~orig.jpg', 'https://images.nasa.gov/details/PIA11984',
     'Kepler Diamond Mine of Stars (first light)', 'NASA/Ames/JPL-Caltech', 'Public domain (NASA)', 'NASA Image and Video Library', 2400),
]


def features():
    for rel, url, page, title, credit, lic, src, mw in FEATURE:
        if rel in credits and os.path.exists(f'{OUT}/{rel}'):
            continue
        try:
            size = save(rel, get(url, 300), mw)
            add(rel, page, title, credit, lic, src, size, file=url)
            print('ok', rel, size)
        except Exception as e:
            print('FAIL', rel, e)


# Survey cutouts: DESI Legacy DR10 where it covers the field, else Pan-STARRS DR1, else DSS2 colour.
SURVEYS = [
    ('CDS/P/DESI-Legacy-Surveys/DR10/color', 'DESI Legacy Imaging Surveys DR10', 'DESI Legacy Imaging Surveys DR10, colour HiPS by CDS; cut with CDS hips2fits', 'Legacy Surveys public data, acknowledgement required; HiPS ODbL-1.0 (CDS)'),
    ('CDS/P/PanSTARRS/DR1/color-z-zg-g', 'Pan-STARRS1 DR1', 'Pan-STARRS1 DR1 (PS1 Science Consortium, via MAST/STScI), colour HiPS by CDS; cut with CDS hips2fits', 'PS1 public data release, acknowledgement required; HiPS ODbL-1.0 (CDS)'),
    ('CDS/P/Skymapper-color-IRG', 'SkyMapper DR1', 'SkyMapper Southern Sky Survey DR1 (ANU), colour HiPS by CDS; cut with CDS hips2fits', 'SkyMapper public data (CC BY 4.0), acknowledgement required; HiPS ODbL-1.0 (CDS)'),
    ('CDS/P/DSS2/color', 'DSS2 colour', 'Digitized Sky Survey 2 (STScI/AURA, Palomar/UK Schmidt), colour HiPS by CDS; cut with CDS hips2fits', 'DSS plates © AURA, Caltech, AAO and UK PPARC; use with the STScI DSS acknowledgement; HiPS ODbL-1.0 (CDS)'),
]


def usable(data):
    im = Image.open(io.BytesIO(data)).convert('RGB').resize((128, 128))
    px = list(im.getdata())
    n = len(px)
    if sum(1 for r, g, b in px if r > 235 and g > 235 and b > 235) / n > 0.2:
        return False
    if sum(1 for r, g, b in px if r + g + b < 12) / n > 0.35:
        return False
    means = [sum(p[i] for p in px) / n + 1 for i in range(3)]
    return max(means) / min(means) < 1.8


def cutout(ra, dec, fov, px=768):
    for hips, short, credit, lic in SURVEYS:
        q = urllib.parse.urlencode({'hips': hips, 'width': px, 'height': px, 'fov': fov, 'projection': 'TAN',
                                    'coordsys': 'icrs', 'ra': f'{ra:.6f}', 'dec': f'{dec:.6f}', 'format': 'jpg'})
        url = f'https://alasky.cds.unistra.fr/hips-image-services/hips2fits?{q}'
        try:
            data = get(url, 90)
        except Exception:
            continue
        if not usable(data):  # outside the footprint (blank) or only one band (false colour)
            continue
        return data, url, short, credit, lic
    return None


def stars():
    hosts = json.load(open(f'{WEB}/public/data/hosts.json'))
    famous = {'WASP-18': 100100827, 'WASP-121': 22529346, 'WASP-43': 36734222, 'TOI-700': 150428135}
    cands = {219345170: (74.8492522, -49.8400446), 29781292: (65.23805051, -68.10264278), 1003831: (130.29516544, -16.03628039),
             150428135: (97.09678555, -65.57931124), 307809773: (99.29499501, 17.56481478), 88863718: (122.58048644, -5.5137852),
             441462736: (353.03363479, -21.80142057), 257060897: (227.53195723, 72.71034628), 1129033: (37.15510833, -7.06066389),
             459837008: (65.05268145, 84.90174347), 1167538: (70.9975879, -31.90650055), 356016119: (254.14323036, 70.02731624),
             278683844: (99.23800201, -58.01526814), 393831507: (187.68647543, 27.45214583)}
    todo = {}
    for n, tic in famous.items():
        i = hosts['tic'].index(tic)
        todo[tic] = (hosts['ra'][i], hosts['dec'][i], n)
    for tic, (ra, dec) in cands.items():
        todo.setdefault(tic, (ra, dec, None))
    for tic, (ra, dec, name) in todo.items():
        rel = f'stars/tic{tic}.jpg'
        if rel in credits and os.path.exists(f'{OUT}/{rel}'):
            continue
        r = cutout(ra, dec, 0.12)
        if not r:
            print('no survey', tic); continue
        data, url, short, credit, lic = r
        size = save(rel, data, 768, 86)
        add(rel, url, f'{short} colour cutout, 7.2′ around {name or "TIC " + str(tic)}', credit, lic, 'CDS hips2fits', size,
            archive=True, ra=ra, dec=dec)
        print('ok', rel, short)


def events():
    ev = json.load(open(f'{WEB}/public/data/events.mock.json'))['events']
    for e in ev:
        sid = e['id'].replace(':', '-').replace('/', '-').replace(' ', '_')
        rel = f'events/{sid}.jpg'
        if rel in credits and os.path.exists(f'{OUT}/{rel}'):
            continue
        imgs = e.get('images') or []
        loc = e.get('location') or {}
        try:
            if imgs:
                im = imgs[0]
                url = im.get('url') or im['thumb_url']
                if 'hips2fits' in url:
                    url = url.replace('width=256', 'width=768').replace('height=256', 'height=768')
                size = save(rel, get(url, 120), 1200, 84)
                add(rel, url, im.get('caption', e['title']), im.get('credit', ''), im.get('licence') or im.get('license') or
                    ('Public domain (NASA)' if 'nasa.gov' in url else 'See credit'), 'event image', size,
                    event=e['id'], kind=im.get('kind'), archive='hips2fits' in url)
                print('ok img', rel)
            elif loc.get('frame') == 'sky' and (loc.get('error_deg') or 1) < 0.01:
                r = cutout(loc['ra_deg'], loc['dec_deg'], 0.05)
                if not r:
                    print('no survey', e['id']); continue
                data, url, short, credit, lic = r
                size = save(rel, data, 768, 86)
                add(rel, url, f'{short} colour cutout, 3′ around {e["title"]}. Archive image taken years before the event.',
                    credit, lic, 'CDS hips2fits', size, event=e['id'], archive=True)
                print('ok cut', rel, short)
            elif e['type'] in ('coronal_mass_ejection', 'geomagnetic_storm', 'solar_flare'):
                t = e['observed_at'].replace('Z', '')
                q = urllib.parse.urlencode({'date': e['observed_at'], 'imageScale': 2.42, 'layers': '[SDO,AIA,AIA,193,1,100]',
                                            'x0': 0, 'y0': 0, 'width': 1024, 'height': 1024, 'display': 'true', 'watermark': 'false'})
                url = f'https://api.helioviewer.org/v2/takeScreenshot/?{q}'
                size = save(rel, get(url, 180), 1024, 86)
                add(rel, url, f'The Sun at 193 Å near {t[:16].replace("T", " ")} UTC (SDO/AIA via Helioviewer)',
                    'NASA/SDO and the AIA, EVE, and HMI science teams; Helioviewer.org', 'Not copyrighted (NASA SDO image-use rules); credit line required',
                    'Helioviewer', size, event=e['id'])
                print('ok sdo', rel)
            else:
                print('tile', e['id'], e['type'])
        except Exception as x:
            print('FAIL', e['id'], str(x)[:160])


if __name__ == '__main__':
    what = sys.argv[1:] or ['features', 'stars', 'events']
    for w in what:
        globals()[w]()
        json.dump(credits, open(CREDITS_PATH, 'w'), indent=1, ensure_ascii=False)
    print(len(credits), 'credited images')
