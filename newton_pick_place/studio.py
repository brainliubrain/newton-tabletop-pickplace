"""Studio rendering of the LIVE physics scene (no replay, no puppet scene).

Pipeline: the physics model compiled by SolverMuJoCo is exported to MJCF,
decorated (lights, skybox, materials, and the FR3 visual meshes that the
newton->mujoco conversion does not carry over), recompiled, and then rendered
frame-by-frame from the REAL simulator state (mjw_data qpos -> mj_data).

Every rendered geometry is either an actual collider of the physics scene
(table, tray, ground — identified through env.shape_roles, never hardcoded
indices) or the authored visual mesh of a simulated body (FR3 links from the
menagerie fr3.xml, bowl lathe, cup asset mesh) attached at the same body
frames. Nothing is hand-modeled or keyframed; there is no CSV replay.
"""

from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FR3_DIR = os.path.join(ASSETS_DIR, "franka_fr3")


def _mjcf_geom_names(shape_indices: list[int]) -> list[str]:
    """newton shape index -> mujoco geom name emitted by SolverMuJoCo."""
    return [f"shape_{i}_{i}" for i in shape_indices]


def _write_lathe_obj(path: str, profile: list[tuple[float, float]], segments: int = 64):
    """Write a smooth hollow lathe mesh (outer or inner surface)."""
    verts: list[tuple[float, float, float]] = []
    norms: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    off = 1
    for i in range(len(profile) - 1):
        r0, z0 = profile[i]
        r1, z1 = profile[i + 1]
        dr, dz = r1 - r0, z1 - z0
        length = math.hypot(dr, dz) or 1.0
        nr, nz = dz / length, -dr / length
        for seg in range(segments):
            a = 2.0 * math.pi * seg / segments
            c, s = math.cos(a), math.sin(a)
            verts.append((r0 * c, r0 * s, z0))
            verts.append((r1 * c, r1 * s, z1))
            norms.append((nr * c, nr * s, nz))
            norms.append((nr * c, nr * s, nz))
        for seg in range(segments):
            seg2 = (seg + 1) % segments
            a0, a1 = off + seg * 2, off + seg * 2 + 1
            b0, b1 = off + seg2 * 2, off + seg2 * 2 + 1
            if r0 > 1e-6 or r1 > 1e-6:
                faces.append((a0, b0, b1))
                faces.append((a0, b1, a1))
        off += segments * 2
    with open(path, "w", encoding="utf-8") as f:
        for v in verts:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for n in norms:
            f.write(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
        for a, b, c in faces:
            f.write(f"f {a}//{a} {b}//{b} {c}//{c}\n")


def _write_mesh_obj(path: str, vertices: np.ndarray, indices: np.ndarray):
    with open(path, "w", encoding="utf-8") as f:
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for i in range(0, len(indices), 3):
            a, b, c = int(indices[i]) + 1, int(indices[i + 1]) + 1, int(indices[i + 2]) + 1
            f.write(f"f {a} {b} {c}\n")


def _ensure_object_meshes(env) -> dict[str, str]:
    """Export the bowl (outer/inner lathe) and cup (authored asset mesh) to OBJ."""
    from env import bowl_profile  # env owns the profile

    outer = os.path.join(ASSETS_DIR, "studio_bowl_outer.obj")
    inner = os.path.join(ASSETS_DIR, "studio_bowl_inner.obj")
    cup = os.path.join(ASSETS_DIR, "studio_cup.obj")
    prof = bowl_profile(env.cfg)
    rt, h = env.cfg.bowl_rim_r, env.cfg.bowl_height
    outer_prof = [(r, z) for r, z in prof if z <= h * 0.92 or r >= rt]  # outer skin only
    _write_lathe_obj(outer, outer_prof)
    _write_lathe_obj(
        inner,
        [
            (rt, h),
            (rt - 0.0065, h * 0.97),
            (rt - 0.0065, 0.007),
            (0.0, 0.005),
        ],
    )
    cup_mesh = env._cup_mesh
    _write_mesh_obj(cup, np.asarray(cup_mesh.vertices), np.asarray(cup_mesh.indices))
    return {"bowl_outer": outer, "bowl_inner": inner, "cup": cup}


def _parse_fr3_visuals() -> tuple[dict[str, str], dict[str, list[dict]]]:
    """Extract materials and per-body visual geoms from the menagerie fr3.xml."""
    tree = ET.parse(os.path.join(FR3_DIR, "fr3.xml"))
    root = tree.getroot()
    materials = {
        m.get("name"): m.get("rgba", "0.5 0.5 0.5 1") for m in root.iter("material") if m.get("name")
    }
    visuals: dict[str, list[dict]] = {}
    for body in root.iter("body"):
        name = body.get("name")
        geoms = [
            {
                "mesh": g.get("mesh"),
                "material": g.get("material"),
                "rgba": g.get("rgba"),
                "pos": g.get("pos", "0 0 0"),
                "quat": g.get("quat"),
            }
            for g in body.findall("geom")
            if g.get("class") == "visual" and g.get("mesh")
        ]
        if geoms and name:
            visuals[name] = geoms
    return materials, visuals


def build_studio_mjcf(env, out_xml: str | None = None) -> str:
    """Export the physics model to MJCF and decorate it into the studio scene.

    The decorated model is structurally identical to the physics model (same
    bodies/joints/qpos layout) — only geoms, assets and lights are added or
    restyled, so physics-state sync stays a plain qpos copy.
    """
    import newton

    if out_xml is None:
        out_xml = os.path.join(ASSETS_DIR, "studio_scene.xml")
    physics_xml = out_xml + ".physics.xml"

    s = newton.solvers.SolverMuJoCo(
        env.model,
        iterations=15,
        ls_iterations=20,
        njmax=512,
        nconmax=256,
        save_to_mjcf=physics_xml,
    )
    del s  # constructed only for the MJCF export

    tree = ET.parse(physics_xml)
    root = tree.getroot()

    # offscreen framebuffer size + shadow quality (the physics mjcf has no
    # <visual> section; the 640x480 default is too small for 1280x720)
    vis = root.find("visual")
    if vis is None:
        vis = ET.Element("visual")
        root.insert(list(root).index(root.find("worldbody")), vis)
    glob = ET.SubElement(vis, "global")
    glob.set("offwidth", "1280")
    glob.set("offheight", "720")
    qual = ET.SubElement(vis, "quality")
    qual.set("shadowsize", "4096")
    qual.set("offsamples", "4")

    # ------------------------------------------------------------------
    # assets: meshes (FR3 visuals + bowl/cup), textures, materials
    # ------------------------------------------------------------------
    meshes = _ensure_object_meshes(env)
    obj_meshes = [(f[:-4], os.path.join(FR3_DIR, f)) for f in sorted(os.listdir(FR3_DIR)) if f.endswith(".obj")]
    obj_meshes += [
        ("studio_bowl_outer", meshes["bowl_outer"]),
        ("studio_bowl_inner", meshes["bowl_inner"]),
        ("studio_cup", meshes["cup"]),
    ]

    asset = ET.Element("asset")
    sky = ET.SubElement(asset, "texture")
    sky.set("name", "skybox")
    sky.set("type", "skybox")
    sky.set("builtin", "gradient")
    sky.set("rgb1", "0.16 0.22 0.32")
    sky.set("rgb2", "0.06 0.08 0.12")
    sky.set("width", "512")
    sky.set("height", "512")
    wood = ET.SubElement(asset, "texture")
    wood.set("name", "wood_tex")
    wood.set("type", "2d")
    wood.set("builtin", "checker")
    wood.set("rgb1", "0.72 0.54 0.34")
    wood.set("rgb2", "0.66 0.49 0.30")
    wood.set("width", "512")
    wood.set("height", "512")
    wood.set("mark", "edge")
    wood.set("markrgb", "0.60 0.44 0.26")
    floor = ET.SubElement(asset, "texture")
    floor.set("name", "floor_tex")
    floor.set("type", "2d")
    floor.set("builtin", "checker")
    floor.set("rgb1", "0.16 0.18 0.22")
    floor.set("rgb2", "0.12 0.14 0.18")
    floor.set("width", "512")
    floor.set("height", "512")
    floor.set("mark", "edge")
    floor.set("markrgb", "0.20 0.22 0.26")

    def _mat(name: str, rgba: str, **kw):
        m = ET.SubElement(asset, "material")
        m.set("name", name)
        m.set("rgba", rgba)
        for k, v in kw.items():
            m.set(k, str(v))

    _mat("oak_wood", "1 1 1 1", texture="wood_tex", texrepeat="6 6", specular="0.25", shininess="0.2")
    _mat("floor_mat", "1 1 1 1", texture="floor_tex", texrepeat="14 14", specular="0.15", shininess="0.1")
    _mat("tray_mat", "0.23 0.26 0.31 1", specular="0.45", shininess="0.35")
    _mat("leg_mat", "0.20 0.22 0.25 1", specular="0.35", shininess="0.3")
    _mat("bowl_out_mat", "0.80 0.36 0.16 1", specular="0.5", shininess="0.4")
    _mat("bowl_in_mat", "0.95 0.92 0.85 1", specular="0.4", shininess="0.35")
    _mat("cup_mat", "0.13 0.50 0.76 1", specular="0.5", shininess="0.4")
    fr3_materials, fr3_visuals = _parse_fr3_visuals()
    for name, rgba in fr3_materials.items():
        _mat(f"fr3_{name}", rgba, specular="0.5", shininess="0.25")
    for mesh_name, path in obj_meshes:
        m = ET.SubElement(asset, "mesh")
        m.set("name", mesh_name)
        m.set("file", path.replace("\\", "/"))

    # MuJoCo merges multiple <asset> sections, but keep ours adjacent to the
    # compiler output for clarity: insert before <worldbody>
    world_el = root.find("worldbody")
    root.insert(list(root).index(world_el), asset)

    # ------------------------------------------------------------------
    # worldbody: lights + restyle physics geoms + inject visual overlays
    # ------------------------------------------------------------------
    world = root.find("worldbody")
    for light_name, pos, dirv, diffuse, cast in (
        ("key_light", "0.65 -0.85 1.6", "-0.18 0.42 -0.85", "0.88 0.85 0.82", "true"),
        ("fill_light", "0.25 0.95 1.3", "0.18 -0.48 -0.82", "0.45 0.50 0.58", "false"),
        ("rim_light", "-0.70 0.0 1.4", "0.75 0.0 -0.68", "0.35 0.38 0.44", "false"),
    ):
        l = ET.SubElement(world, "light")
        l.set("name", light_name)
        l.set("pos", pos)
        l.set("dir", dirv)
        l.set("diffuse", diffuse)
        l.set("specular", "0.4 0.4 0.4")
        l.set("castshadow", cast)

    geom_by_name = {g.get("name"): g for g in root.iter("geom") if g.get("name")}
    roles = env.shape_roles

    def _restyle_role(role: str, material: str | None = None, rgba: str | None = None, hidden: bool = False):
        for idx in roles.get(role, []):
            for gname in _mjcf_geom_names([idx]):
                g = geom_by_name.get(gname)
                if g is None:
                    continue
                if material:
                    g.set("material", material)
                if rgba:
                    g.set("rgba", rgba)
                if hidden:
                    # collision-only shapes with a visual overlay: keep the
                    # collider, drop it out of the default render groups
                    g.set("group", "3")
                    g.set("rgba", "0.5 0.5 0.5 0.0")

    _restyle_role("table_top", material="oak_wood")
    _restyle_role("table_legs", material="leg_mat")
    _restyle_role("table_stand", material="leg_mat")
    _restyle_role("tray", material="tray_mat")
    for idx in roles.get("ground", []):  # planes are named ground_plane_{i}
        g = geom_by_name.get(f"ground_plane_{idx}")
        if g is not None:
            g.set("material", "floor_mat")
    _restyle_role("bowl_collision", hidden=True)
    _restyle_role("cup_collision", hidden=True)
    # arm collision hulls + finger boxes: hidden, replaced by fr3 visual meshes
    for i in range(7, 54):
        g = geom_by_name.get(f"shape_{i}_{i}")
        if g is not None:
            g.set("group", "3")
            g.set("rgba", "0.5 0.5 0.5 0.0")

    # FR3 visual overlays: menagerie body fr3_*  ->  physics body fr3_fr3_*
    def _body_el(bname: str):
        for b in root.iter("body"):
            if b.get("name") == bname:
                return b
        return None

    def _visual_geom(target, mesh: str, material: str | None, rgba: str | None, pos: str, quat: str | None):
        g = ET.SubElement(target, "geom")
        g.set("type", "mesh")  # mujoco 3.15 does not infer type from mesh=
        g.set("mesh", mesh)
        g.set("contype", "0")
        g.set("conaffinity", "0")
        g.set("group", "2")
        g.set("pos", pos)
        if quat:
            g.set("quat", quat)
        if material:
            g.set("material", material)
        elif rgba:
            g.set("rgba", rgba)
        return g

    for mbname, geoms in fr3_visuals.items():
        target = _body_el(f"fr3_{mbname}")
        if target is None:
            print(f"[studio] WARNING: no physics body for menagerie body {mbname}")
            continue
        for gspec in geoms:
            _visual_geom(
                target,
                gspec["mesh"],
                f"fr3_{gspec['material']}" if gspec["material"] else None,
                gspec["rgba"],
                gspec["pos"],
                gspec["quat"],
            )

    # bowl / cup visual overlays (hollow ceramic look, same body frames).
    # Objects imported via real2sim asset packs render from their OWN visual
    # mesh with the manifest material (translucent cups keep alpha < 1).
    for obj_name, default_overlay in (
        ("bowl", [("studio_bowl_outer", "bowl_out_mat"), ("studio_bowl_inner", "bowl_in_mat")]),
        ("cup", [("studio_cup", "cup_mat")]),
    ):
        body_el = _body_el(obj_name)
        manifest = env.asset_manifests.get(obj_name)
        if manifest is not None:
            pack_dir = manifest["pack_dir"]
            m = ET.SubElement(asset, "mesh")
            m.set("name", f"pack_{obj_name}")
            m.set("file", os.path.join(pack_dir, manifest["visual"]["file"]).replace("\\", "/"))
            pm = ET.SubElement(asset, "material")
            pm.set("name", f"pack_{obj_name}_mat")
            pm.set("rgba", manifest["rgba"])
            _visual_geom(body_el, f"pack_{obj_name}", f"pack_{obj_name}_mat", None, "0 0 0", None)
        else:
            for mesh_name, mat_name in default_overlay:
                _visual_geom(body_el, mesh_name, mat_name, None, "0 0 0", None)

    tree.write(out_xml, encoding="utf-8", xml_declaration=True)
    return out_xml


class StudioRenderer:
    """Render frames of the live physics scene with studio lighting."""

    def __init__(self, env, width: int = 1280, height: int = 720):
        import imageio.v2 as imageio  # noqa: F401  (ensures the ffmpeg binary is present)

        xml_path = build_studio_mjcf(env)
        self.model = mujoco.MjModel.from_xml_path(xml_path)
        assert self.model.nq == env.solver.mj_model.nq, "studio model out of sync with physics"
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=height, width=width)
        self.cam = mujoco.MjvCamera()
        self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.cam.lookat[:] = [0.42, 0.02, 0.42]
        self.cam.distance = 1.30
        self.cam.azimuth = -130
        self.cam.elevation = -24
        self.width, self.height = width, height
        self._font = None
        try:
            from PIL import ImageFont

            self._font = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 15)
        except Exception:
            pass

    def render_frame(self, env, hud: dict | None = None) -> np.ndarray:
        from PIL import Image, ImageDraw

        # sync the joint state (identical qpos layout) — the studio model adds
        # only visual geoms/assets/lights, never bodies or joints
        qpos = env.solver.mjw_data.qpos.numpy()[0][: self.model.nq]
        self.data.qpos[:] = qpos
        mujoco.mj_forward(self.model, self.data)
        self.renderer.update_scene(self.data, camera=self.cam)
        rgb = self.renderer.render()
        if hud:
            img = Image.fromarray(rgb)
            draw = ImageDraw.Draw(img, "RGBA")
            draw.rectangle([0, self.height - 34, self.width, self.height], fill=(13, 17, 23, 210))
            ee = hud.get("ee", (0, 0, 0))
            line = (
                f"t={hud.get('t', 0):5.1f}s  PHASE {hud.get('phase', ''):<18} "
                f"GAP {hud.get('gap', 0) * 1000:4.0f}mm  "
                f"EE ({ee[0]:.2f},{ee[1]:.2f},{ee[2]:.2f})m"
            )
            draw.text((14, self.height - 27), line, fill=(200, 210, 220, 255), font=self._font)
            if hud.get("success"):
                draw.rounded_rectangle(
                    [self.width - 200, self.height - 30, self.width - 14, self.height - 6],
                    radius=4,
                    fill=(35, 134, 54, 230),
                )
                draw.text((self.width - 190, self.height - 27), "TASK SOLVED", fill=(255, 255, 255, 255), font=self._font)
            rgb = np.asarray(img)
        return rgb

    def close(self):
        self.renderer.close()
