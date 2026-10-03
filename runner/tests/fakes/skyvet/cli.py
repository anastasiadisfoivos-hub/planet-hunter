"""Stand-in for skyvet: adds a vetting block with verdict "flag"."""
import argparse
import json

p = argparse.ArgumentParser()
p.add_argument("candidate")
p.add_argument("-o", "--out")
p.add_argument("--tri-budget")
a = p.parse_args()
c = json.load(open(a.candidate))
c["vetting"] = {"summary": {"verdict": "flag", "reasons": ["test stand-in: no tools ran"]}}
if a.out:
    json.dump(c, open(a.out, "w"))
print(json.dumps(c["vetting"]))
