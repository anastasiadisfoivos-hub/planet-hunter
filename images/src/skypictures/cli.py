"""skypictures CLI: add real pictures to every event in an events.json.

    skypictures events.json -o events.with-pictures.json

Accepts a JSON list of events or an object with an "events" list (kept as is otherwise).
Writes, next to the output:
  <out>.thumbs.json   {full image url: thumbnail url} (the contract's Image has one url)
  pictures-cache/     copies of images whose source deletes them within a day (NOAA OVATION)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import mimetypes
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from .core import Stats, order, pictures_for, thumbnail_url, validate
from .earth import EPHEMERAL_PREFIXES
from .models import Event, Image
from .net import FetchError, get_net

log = logging.getLogger("skypictures")


def load_events(doc) -> list[Event]:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("events"), list):
        return doc["events"]
    raise SystemExit("input must be a JSON list of events or an object with an 'events' list")


def rehost(img: Image, folder: Path, base_url: str) -> Image:
    """Copy an image whose source URL will vanish into `folder`; point the image at the copy."""
    ctype, body = get_net().download(img["url"])
    ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or Path(urlsplit(img["url"]).path).suffix
    name = Path(urlsplit(img["url"]).path).stem + "-" + hashlib.sha256(img["url"].encode()).hexdigest()[:8] + ext
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(body)
    return {**img, "url": f"{base_url.rstrip('/')}/{name}"}


def enrich_event(event: Event, *, check: bool, replace: bool, stats: Stats) -> Event:
    new = pictures_for(event, check=check, stats=stats)
    existing = [] if replace else list(event.get("images") or [])
    if existing and check:
        existing = validate(existing, stats)
    return {**event, "images": order(new + existing)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skypictures", description=__doc__.split("\n\n")[0])
    ap.add_argument("events", type=Path, help="input events.json")
    ap.add_argument("-o", "--out", type=Path, help="output file (default: overwrite input)")
    ap.add_argument("--no-check", action="store_true", help="do not fetch URLs to drop dead ones")
    ap.add_argument("--replace", action="store_true", help="drop images the events already had")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--rehost-dir", type=Path, help="default: <out dir>/pictures-cache")
    ap.add_argument("--rehost-base", default="pictures-cache", help="URL prefix the site serves --rehost-dir at")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    out = args.out or args.events
    doc = json.loads(args.events.read_text())
    events = load_events(doc)
    stats = Stats()
    check = not args.no_check

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        enriched = list(pool.map(lambda e: enrich_event(e, check=check, replace=args.replace, stats=stats),
                                 events))

    rehost_dir = args.rehost_dir or out.parent / "pictures-cache"
    rehosted = 0
    for ev in enriched:
        for i, img in enumerate(ev["images"]):
            if img["url"].startswith(EPHEMERAL_PREFIXES):
                try:
                    ev["images"][i] = rehost(img, rehost_dir, args.rehost_base)
                    rehosted += 1
                except FetchError as exc:
                    log.warning("could not re-host %s: %s", img["url"], exc)

    thumbs: dict[str, str] = {}
    for ev in enriched:
        for img in ev["images"]:
            t = thumbnail_url(img["url"])
            thumbs[img["url"]] = t if (t == img["url"] or not check or get_net().probe(t).ok) else img["url"]

    if isinstance(doc, dict):
        doc = {**doc, "events": enriched}
    else:
        doc = enriched
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    thumbs_path = out.with_name(out.stem + ".thumbs.json")
    thumbs_path.write_text(json.dumps(thumbs, indent=1) + "\n")

    kinds = Counter(img["kind"] for ev in enriched for img in ev["images"])
    with_pics = sum(1 for ev in enriched if ev["images"])
    print(f"{len(enriched)} events, {with_pics} with pictures; images by kind: {dict(kinds)}", file=sys.stderr)
    if check:
        rate = len(stats.dropped) / stats.candidates if stats.candidates else 0.0
        print(f"checked {stats.candidates} URLs, dropped {len(stats.dropped)} dead/blank ({rate:.1%})",
              file=sys.stderr)
        for url, reason in stats.dropped:
            print(f"  dropped {reason}: {url}", file=sys.stderr)
    for msg in stats.provider_errors:
        print(f"  source error {msg}", file=sys.stderr)
    if rehosted:
        print(f"re-hosted {rehosted} short-lived image(s) into {rehost_dir}", file=sys.stderr)
    print(f"wrote {out} and {thumbs_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
