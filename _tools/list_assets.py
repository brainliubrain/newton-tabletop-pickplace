import json
import sys

d = json.load(open(sys.argv[1]))
prefix = sys.argv[2] if len(sys.argv) > 2 else ""
for e in d["tree"]:
    if e["type"] == "blob" and e["path"].startswith(prefix):
        print(f'{e.get("size", 0):9d}  {e["path"]}')
