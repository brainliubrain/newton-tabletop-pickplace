"""Vendoring of Franka FR3 visual meshes (OBJ) from menagerie at the pinned SHA.

Walks the git tree via the GitHub API (repo root -> franka_fr3 -> assets),
downloads every .obj into newton_pick_place/assets/franka_fr3/, and also saves
the menagerie fr3.xml (visual geom declarations) for the overlay generator.
"""
import json
import os
import sys
import time
import urllib.request

API = "https://api.github.com/repos/google-deepmind/mujoco_menagerie/git/trees/"
RAW = "https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/da76818e269b82289eba39808e2fb91d679d6994/"
SHA = "da76818e269b82289eba39808e2fb91d679d6994"
W = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(W, "newton_pick_place", "assets", "franka_fr3")


def get_json(url: str):
    for a in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            print("retry", a, e)
            time.sleep(2)
    raise RuntimeError(url)


def fetch(url: str, dest: str):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for a in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
            with open(dest, "wb") as f:
                f.write(data)
            return len(data)
        except Exception as e:  # noqa: BLE001
            print("retry", a, e)
            time.sleep(2)
    raise RuntimeError(url)


def main() -> int:
    root = get_json(API + SHA)
    fr3 = next(e for e in root["tree"] if e["path"] == "franka_fr3")
    sub = get_json(API + fr3["sha"])
    assets = next(e for e in sub["tree"] if e["path"] == "assets")
    leaves = get_json(API + assets["sha"])
    objs = [e for e in leaves["tree"] if e["type"] == "blob" and e["path"].endswith(".obj")]
    print(f"{len(objs)} obj files, {sum(e['size'] for e in objs) / 1e6:.1f} MB")
    ok = True
    for e in objs:
        dest = os.path.join(OUT, e["path"].split("/")[-1])
        if os.path.exists(dest) and os.path.getsize(dest) == e["size"]:
            continue
        n = fetch(RAW + "franka_fr3/assets/" + e["path"], dest)
        print(f"  {e['path'].split('/')[-1]} {n / 1e3:.0f} KB", flush=True)
    # also the fr3.xml (visual geom declarations) and its meshdir assets
    for extra in ("franka_fr3/fr3.xml",):
        dest = os.path.join(OUT, extra.split("/")[-1])
        n = fetch(RAW + extra, dest)
        print(f"  {extra.split('/')[-1]} {n / 1e3:.1f} KB")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
