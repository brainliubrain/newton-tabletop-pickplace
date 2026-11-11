import json
import os
import sys

W = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
d = json.load(open(os.path.join(W, "_tmp_menagerie.json")))
print("truncated:", d.get("truncated"), "entries:", len(d.get("tree", [])))
fr3 = [e for e in d["tree"] if e["path"].startswith("franka_fr3/") and e["type"] == "blob"]
print("franka_fr3 files:", len(fr3))
import collections

exts = collections.Counter(e["path"].rsplit(".", 1)[-1] for e in fr3)
print(dict(exts))
objs = [e for e in fr3 if e["path"].endswith(".obj")]
print("total obj bytes:", sum(e.get("size", 0) for e in objs))
for e in fr3:
    if not e["path"].endswith(".obj"):
        print(" ", e["path"], e.get("size", 0))
