"""Check the target list's predicted TGLC sectors against the files that exist (HEAD requests):
the first 10 rows and 20 random tier-1 rows (seed 3).

    uv run python scripts/spotcheck.py targets/targets_faint_top.csv > results/targets_spotcheck.json
"""

import csv
import json
import random
import sys

from skyfaint import tglc

rows = list(csv.DictReader(open(sys.argv[1])))
t1 = [r for r in rows if r["tier"] == "1"]
random.seed(3)
pick = rows[:10] + random.sample(t1[10:], 20)
res = []
for r in pick:
    idx = tglc.resolve(int(r["tic"]))
    p = set(map(int, r["sectors"].split()))
    q = {f["sector"] for f in idx["files"]}
    res.append({"tic": int(r["tic"]), "tmag": float(r["tmag"]), "gaia_digits": len(str(idx["gaia_dr3"])),
                "predicted": len(p), "published": len(q), "missing": sorted(p - q), "extra": sorted(q - p)})
summary = {"stars": len(res), "predicted_sectors": sum(x["predicted"] for x in res),
           "published_of_predicted": sum(x["predicted"] - len(x["missing"]) for x in res),
           "extra_found": sum(len(x["extra"]) for x in res),
           "identical_sets": sum(not x["missing"] and not x["extra"] for x in res),
           "stars_without_files": sum(x["published"] == 0 for x in res)}
print(json.dumps({"summary": summary, "stars": res}, indent=1))
