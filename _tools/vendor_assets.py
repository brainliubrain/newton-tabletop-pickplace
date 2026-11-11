"""Vendor newton-assets files from raw.githubusercontent into the project.

Usage: py -3.11 _tools/vendor_assets.py <tree.json> <output_dir> <prefix> [<prefix> ...]
Downloads every blob whose path starts with one of the prefixes.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

SHA = "f8fb7abcbeba2318814a74f3eeb02780ad7925d6"
BASE = f"https://raw.githubusercontent.com/newton-physics/newton-assets/{SHA}/"


def fetch(url: str, dest: str, retries: int = 3) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"    retry {attempt + 1}: {e}", flush=True)
            time.sleep(2 * (attempt + 1))
    return False


def main() -> int:
    tree_json, out_dir = sys.argv[1], sys.argv[2]
    prefixes = tuple(sys.argv[3:])
    d = json.load(open(tree_json))
    blobs = [e["path"] for e in d["tree"] if e["type"] == "blob" and e["path"].startswith(prefixes)]
    print(f"{len(blobs)} files to vendor")
    ok = True
    for i, p in enumerate(blobs):
        dest = os.path.join(out_dir, p.replace("/", os.sep))
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"[{i + 1}/{len(blobs)}] skip (cached) {p}")
            continue
        print(f"[{i + 1}/{len(blobs)}] {p}", flush=True)
        if not fetch(BASE + p, dest):
            ok = False
            print(f"FAILED: {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
