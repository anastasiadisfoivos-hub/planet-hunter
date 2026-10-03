# Faint TESS footprints for the /log sky map: run with a Python that has tess-point (pip install tess-point).
#   python build_sectors.py ../../../public/data/monitor/sectors.json

import json, sys
import tess_stars2px as t
out = {"source": "tess-point (tess_stars2px_reverse_function_entry), CCD science area, columns 45-2092, rows 1-2048", "sectors": []}
for sec in (104, 105, 106):
    ccds = []
    for cam in (1, 2, 3, 4):
        for ccd in (1, 2, 3, 4):
            edge = []
            n = 10
            pts = [(45 + 2047 * k / n, 1) for k in range(n + 1)] + [(2092, 1 + 2047 * k / n) for k in range(1, n + 1)] \
                + [(2092 - 2047 * k / n, 2048) for k in range(1, n + 1)] + [(45, 2048 - 2047 * k / n) for k in range(1, n + 1)]
            for c, r in pts:
                ra, dec, _ = t.tess_stars2px_reverse_function_entry(sec, cam, ccd, c, r)
                edge.append([round(float(ra), 2), round(float(dec), 2)])
            ccds.append({"camera": cam, "ccd": ccd, "edge": edge})
    out["sectors"].append({"sector": sec, "ccds": ccds})
json.dump(out, open(sys.argv[1], "w"), separators=(",", ":"))
print("ok", len(out["sectors"]))
