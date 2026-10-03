"""`python -m hunt merge DIRS --out OUT [--sensitivity F]`: the shapes hunt's merge writes."""
import argparse
import json
import shutil
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("cmd")
p.add_argument("dirs", nargs="+")
p.add_argument("--out", required=True)
p.add_argument("--sensitivity")
a = p.parse_args()
out = Path(a.out)
(out / "candidates").mkdir(parents=True, exist_ok=True)
cands, n_stars = {}, 0
for d in map(Path, a.dirs):
    n_stars += len(list((d / "results").glob("*.json")))
    for c in sorted((d / "candidates").glob("*.json")):
        shutil.copy(c, out / "candidates" / c.name)
        cands[c.stem] = json.loads(c.read_text())
index = [{"file": f"candidates/{k}.json", "id": v["id"], "tic": v["tic"], "score": v["score"]} for k, v in cands.items()]
funnel = {"stars_searched": n_stars, "candidates": len(index)}
(out / "candidates.json").write_text(json.dumps({"funnel": funnel, "candidates": index, "rejected_at_merge": {}}))
(out / "summary.json").write_text(json.dumps({"funnel": funnel, "n_candidates": len(index), "shards": []}))
sys.exit(0)
