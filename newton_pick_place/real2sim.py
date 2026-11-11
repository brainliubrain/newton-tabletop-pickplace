"""real2sim asset-import pipeline: real-world captures -> simulation-ready assets.

Turns a mesh captured from a real object (phone photogrammetry OBJ/PLY/GLB,
or a CAD export STL) into an asset pack the simulation can load directly:

    assets/real2sim/<name>/
      object.json        manifest: mass, friction, collision spec, bbox, category,
                         spawn offset, optional rgba (e.g. translucent cup)
      visual.obj         decimated render mesh
      collision_*.obj    convex collision parts (CoACD decomposition or single hull)

Then wire it into the environment:

    env = PickPlaceEnv(object_assets={"cup": "assets/real2sim/my_cup"})

The physics uses the collision parts; the studio renderer uses the visual mesh
with the manifest's material (transparent cups get alpha < 1). The procedural
objects remain the default when no asset pack is given.

CLI:
    python real2sim.py import-object --name my_cup --mesh scan.obj --mass 0.30 \
        --category cup --transparent
    python real2sim.py preview --name my_cup
    python real2sim.py list

Measured-real workflow (cheapest real2sim): caliper the object, weigh it on a
kitchen scale, pass --mass; the density is derived from the mesh volume so the
simulated inertia matches the real object. Friction defaults to the category
value and can be calibrated later (see docs/REAL2SIM.md).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
R2S_DIR = os.path.join(ASSETS_DIR, "real2sim")

# default material parameters per category (calibrate against reality later;
# docs/REAL2SIM.md documents the slip-angle calibration recipe)
CATEGORY_DEFAULTS = {
    "bowl": {"mu": 0.8, "rgba": "0.80 0.36 0.16 1"},
    "cup": {"mu": 0.8, "rgba": "0.13 0.50 0.76 0.55"},  # translucent by default
    "tray": {"mu": 0.6, "rgba": "0.23 0.26 0.31 1"},
    "object": {"mu": 0.8, "rgba": "0.6 0.6 0.6 1"},
}

MAX_VISUAL_FACES = 20000
MAX_COLLISION_HULLS = 16


def _trimesh():
    import trimesh

    return trimesh


def load_mesh(path: str, up_axis: str = "z", scale: float = 1.0):
    """Load a scan/CAD mesh and normalize: rotate up-axis, scale, base-center."""
    tm = _trimesh()
    mesh = tm.load(path, force="mesh")
    if mesh is None or len(mesh.vertices) == 0:
        raise ValueError(f"could not load mesh from {path}")
    if up_axis.lower() == "y":
        mesh.apply_transform(tm.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    elif up_axis.lower() == "x":
        mesh.apply_transform(tm.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    if abs(scale - 1.0) > 1e-9:
        mesh.apply_scale(scale)
    # base-center: origin at the bottom center, object standing on z=0
    b = mesh.bounds
    center_xy = (b[0][:2] + b[1][:2]) / 2.0
    mesh.apply_translation([-center_xy[0], -center_xy[1], -b[0][2]])
    return mesh


def make_visual(mesh, out_obj: str, max_faces: int = MAX_VISUAL_FACES) -> dict:
    """Decimate the scan into a render mesh and export OBJ."""
    visual = mesh
    if len(visual.faces) > max_faces:
        try:
            visual = visual.simplify_quadric_decimation(max_faces)
        except Exception as e:  # noqa: BLE001
            print(f"    [warn] decimation failed ({e!r}); using full mesh")
    visual.export(out_obj)
    return {"file": os.path.basename(out_obj), "faces": int(len(visual.faces))}


def make_collision(mesh, out_prefix: str, mode: str = "auto", max_hulls: int = MAX_COLLISION_HULLS) -> dict:
    """Build collision geometry: CoACD convex decomposition (or single hull).

    Returns a manifest fragment. Parts are exported as collision_###.obj; each
    part is convex, so simulators use it directly (mujoco: mesh->convex hull).
    """
    tm = _trimesh()
    parts: list = []
    used = mode
    if mode in ("auto", "decomp"):
        try:
            import coacd

            coacd.set_log_level("error")
            cmesh = coacd.Mesh(np.asarray(mesh.vertices), np.asarray(mesh.faces))
            result = coacd.run_coacd(cmesh, threshold=0.05, max_convex_hull=max_hulls)
            parts = [tm.Trimesh(v, f) for v, f in result if len(f) >= 4]
            used = "decomp"
        except ImportError:
            if mode == "decomp":
                raise
            print("    [warn] coacd not installed; falling back to convex hull")
    if not parts:
        parts = [mesh.convex_hull]
        used = "hull"

    files = []
    for i, part in enumerate(parts):
        fpath = f"{out_prefix}_{i:03d}.obj"
        part.export(fpath)
        files.append(os.path.basename(fpath))
    total = sum(len(p.faces) for p in parts)
    return {"mode": used, "files": files, "parts": len(parts), "faces": int(total)}


def import_object(
    name: str,
    mesh_path: str,
    mass_kg: float | None = None,
    mu: float | None = None,
    category: str = "object",
    transparent: bool = False,
    collision_mode: str = "auto",
    up_axis: str = "z",
    scale: float = 1.0,
    density_override: float | None = None,
) -> str:
    """Import one object into assets/real2sim/<name>/ and return the pack dir."""
    tm = _trimesh()
    out_dir = os.path.join(R2S_DIR, name)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[real2sim] importing {mesh_path} -> {out_dir}")
    mesh = load_mesh(mesh_path, up_axis=up_axis, scale=scale)
    extents = mesh.extents
    volume = abs(float(mesh.volume)) if mesh.is_watertight else float(mesh.convex_hull.volume)
    print(f"    bbox {(extents * 1000).round(0)} mm (xyz), volume {volume * 1e6:.1f} cm^3")

    visual_info = make_visual(mesh, os.path.join(out_dir, "visual.obj"))
    collision_info = make_collision(mesh, os.path.join(out_dir, "collision"), mode=collision_mode)

    # mass -> density: the sim derives inertia from mesh volume * density, so
    # matching the real mass means the dynamics match the real object
    mass = mass_kg if mass_kg is not None else 0.20
    density = mass / max(volume, 1e-9)

    defaults = CATEGORY_DEFAULTS.get(category, CATEGORY_DEFAULTS["object"])
    rgba = defaults["rgba"]
    if transparent:
        # keep the hue, force alpha for a translucent look
        parts_rgba = rgba.split()
        rgba = f"{parts_rgba[0]} {parts_rgba[1]} {parts_rgba[2]} 0.45"

    manifest = {
        "name": name,
        "category": category,
        "source_mesh": os.path.abspath(mesh_path),
        "up_axis": up_axis,
        "scale": scale,
        "bbox_m": [round(float(v), 5) for v in extents],
        "volume_m3": round(volume, 8),
        "mass_kg": round(mass, 4),
        "density": round(density, 2),
        "mu": mu if mu is not None else defaults["mu"],
        "rgba": rgba,
        "transparent": bool(transparent),
        "origin": "base-center (standing on z=0)",
        "visual": visual_info,
        "collision": collision_info,
        "spawn_clearance_m": 0.002,
    }
    with open(os.path.join(out_dir, "object.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(
        f"    visual {visual_info['faces']} faces | collision {collision_info['mode']} "
        f"x{collision_info['parts']} | density {density:.0f} kg/m^3 | mu {manifest['mu']}"
    )
    return out_dir


def load_asset_pack(path_or_name: str) -> dict:
    """Load an asset pack manifest by name or directory."""
    pack_dir = path_or_name if os.path.isdir(path_or_name) else os.path.join(R2S_DIR, path_or_name)
    manifest_path = os.path.join(pack_dir, "object.json")
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"not an asset pack (missing object.json): {pack_dir}")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest["pack_dir"] = pack_dir
    return manifest


def build_newton_shapes(builder, manifest: dict, body: int, cfg_contact):
    """Add a loaded asset pack to a newton ModelBuilder as a simulated body.

    Visual mesh = render-only; collision parts = the real colliders; density
    from the manifest so the measured mass is reproduced. Returns the visual
    newton.Mesh.
    """
    import newton
    import warp as wp

    pack_dir = manifest["pack_dir"]
    visual_mesh = _trimesh().load(os.path.join(pack_dir, manifest["visual"]["file"]), force="mesh")
    visual = newton.Mesh(
        np.asarray(visual_mesh.vertices, dtype=np.float32),
        np.asarray(visual_mesh.faces, dtype=np.int32).ravel(),
    )
    builder.add_shape_mesh(
        body=body,
        mesh=visual,
        cfg=cfg_contact(has_shape_collision=False, density=0.0),  # render-only; density=0 so it adds no phantom mass on top of the collision parts
    )
    for part_file in manifest["collision"]["files"]:
        part = _trimesh().load(os.path.join(pack_dir, part_file), force="mesh")
        builder.add_shape_mesh(
            body=body,
            mesh=newton.Mesh(
                np.asarray(part.vertices, dtype=np.float32),
                np.asarray(part.faces, dtype=np.int32).ravel(),
            ),
            xform=wp.transform(),
            cfg=cfg_contact(density=float(manifest["density"]), mu=float(manifest["mu"])),
        )
    return visual


def preview(name: str, out_png: str | None = None) -> str:
    """Render a standalone preview of an asset pack (visual + collision wires)."""
    import mujoco
    from PIL import Image

    manifest = load_asset_pack(name)
    pack_dir = manifest["pack_dir"]
    meshes_xml = "".join(
        f'<mesh name="coll_{i}" file="{os.path.join(pack_dir, f).replace(chr(92), "/")}"/>'
        for i, f in enumerate(manifest["collision"]["files"])
    )
    coll_geoms = "".join(
        f'<geom type="mesh" mesh="coll_{i}" rgba="0.2 0.7 0.3 0.35"/>'
        for i in range(len(manifest["collision"]["files"]))
    )
    xml = f"""
<mujoco>
  <asset>
    <mesh name="visual" file="{os.path.join(pack_dir, manifest['visual']['file']).replace(chr(92), '/')}"/>
    {meshes_xml}
  </asset>
  <worldbody>
    <light pos="0.4 -0.6 1.0" dir="0 0.3 -1" diffuse="0.9 0.9 0.9"/>
    <geom type="plane" size="0.5 0.5 0.1" rgba="0.25 0.27 0.3 1"/>
    <body pos="0 0 0.01">
      <freejoint/>
      <geom type="mesh" mesh="visual" rgba="{manifest['rgba']}"/>
      {coll_geoms}
    </body>
  </worldbody>
</mujoco>
"""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    r = mujoco.Renderer(model, height=480, width=640)
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = [0, 0, manifest["bbox_m"][2] / 2]
    cam.distance = max(manifest["bbox_m"]) * 3.5
    cam.azimuth = -55
    cam.elevation = -20
    r.update_scene(data, camera=cam)
    img = r.render()
    r.close()
    out_png = out_png or os.path.join(pack_dir, "preview.png")
    Image.fromarray(img).save(out_png)
    print(f"[real2sim] preview -> {out_png}")
    return out_png


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_imp = sub.add_parser("import-object", help="scan/CAD mesh -> asset pack")
    p_imp.add_argument("--name", required=True)
    p_imp.add_argument("--mesh", required=True)
    p_imp.add_argument("--mass", type=float, default=None, help="measured mass in kg (kitchen scale)")
    p_imp.add_argument("--mu", type=float, default=None, help="friction coefficient (else category default)")
    p_imp.add_argument("--category", default="object", choices=list(CATEGORY_DEFAULTS))
    p_imp.add_argument("--transparent", action="store_true", help="translucent material (glass cup)")
    p_imp.add_argument("--collision", default="auto", choices=["auto", "hull", "decomp"])
    p_imp.add_argument("--up", default="z", choices=["x", "y", "z"], help="up axis of the scan")
    p_imp.add_argument("--scale", type=float, default=1.0, help="uniform scale (e.g. 0.001 for mm scans)")

    p_prev = sub.add_parser("preview", help="render an asset pack preview png")
    p_prev.add_argument("--name", required=True)

    sub.add_parser("list", help="list imported asset packs")

    args = parser.parse_args()
    if args.cmd == "import-object":
        import_object(
            name=args.name,
            mesh_path=args.mesh,
            mass_kg=args.mass,
            mu=args.mu,
            category=args.category,
            transparent=args.transparent,
            collision_mode=args.collision,
            up_axis=args.up,
            scale=args.scale,
        )
    elif args.cmd == "preview":
        preview(args.name)
    elif args.cmd == "list":
        if os.path.isdir(R2S_DIR):
            for d in sorted(os.listdir(R2S_DIR)):
                mf = os.path.join(R2S_DIR, d, "object.json")
                if os.path.isfile(mf):
                    with open(mf, encoding="utf-8") as f:
                        m = json.load(f)
                    print(
                        f"{d:20s} category={m['category']:8s} mass={m['mass_kg']}kg "
                        f"collision={m['collision']['mode']}"
                    )
        else:
            print("(no imported assets yet)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
