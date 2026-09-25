"""Record NOAA's OVATION listing + one frame check for the geomagnetic-storm tests.

No storm was active when the examples were recorded (DONKI's last one is older than SWPC's
24-hour frame archive), so the test event here is a TEST INPUT pinned to a frame time that
existed at recording, not a claimed real storm.

    uv run python scripts/record_noaa.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from recording import FIXTURES, recording

from skypictures import pictures_for
from skypictures.earth import OVATION
from skypictures.net import get_net

with recording("noaa"):
    html = get_net().text(f"{OVATION}/north/", ttl=0)
    day, hhmm = re.findall(r"aurora_N_(\d{4}-\d{2}-\d{2})_(\d{4})\.jpg", html)[-1]
    event = {"id": "test:storm", "type": "geomagnetic_storm", "title": "test storm", "summary": "",
             "source": "test", "source_url": "", "observed_at": f"{day}T{hhmm[:2]}:{hhmm[2:]}:40Z",
             "reported_at": "", "location": {"frame": "earth", "lat_deg": 64.8, "lon_deg": -147.7, "alt_km": None},
             "confidence": 1.0, "confidence_basis": "", "brightness_mag": None, "images": [], "raw": {}}
    pics = pictures_for(event)
(FIXTURES / "noaa_event.json").write_text(json.dumps({"event": event, "pictures": pics}, indent=1) + "\n")
print(json.dumps(pics, indent=1))
