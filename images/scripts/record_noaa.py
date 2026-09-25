"""Record NOAA's "latest" aurora-map checks for the geomagnetic-storm tests.

No storm was active when the examples were recorded (DONKI's last one is older than 24 h), so
the test event here is a TEST INPUT, a storm said to have begun 2 h before recording, not a
claimed real storm.

    uv run python scripts/record_noaa.py
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from recording import FIXTURES, recording

from skypictures import pictures_for

now = datetime.now(UTC).replace(microsecond=0)
event = {"id": "test:storm", "type": "geomagnetic_storm", "title": "test storm", "summary": "",
         "source": "test", "source_url": "", "observed_at": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
         "reported_at": "", "location": {"frame": "earth", "lat_deg": None, "lon_deg": None, "alt_km": None},
         "confidence": 1.0, "confidence_basis": "", "brightness_mag": None, "images": [], "raw": {}}
with recording("noaa"):
    pics = pictures_for(event)
doc = {"now": now.isoformat().replace("+00:00", "Z"), "event": event, "pictures": pics}
(FIXTURES / "noaa_event.json").write_text(json.dumps(doc, indent=1) + "\n")
print(json.dumps(pics, indent=1))
