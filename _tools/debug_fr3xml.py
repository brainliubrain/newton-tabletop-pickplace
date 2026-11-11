import os
import xml.etree.ElementTree as ET

FR3_DIR = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "newton_pick_place",
    "assets",
    "franka_fr3",
)
tree = ET.parse(os.path.join(FR3_DIR, "fr3.xml"))
root = tree.getroot()
mats = {m.get("name"): m.get("rgba") for m in root.iter("material") if m.get("name")}
print("materials:", len(mats))
for body in root.iter("body"):
    geoms = [g for g in body.findall("geom") if g.get("class") == "visual" and g.get("mesh")]
    if geoms:
        print(body.get("name"), len(geoms), [g.get("material") or g.get("rgba") for g in geoms][:3])
