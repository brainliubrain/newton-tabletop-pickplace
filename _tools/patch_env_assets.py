"""Patch env.py: optional real2sim asset packs for bowl/cup (imported vs procedural).

Whole-section replacements with idempotence guard.
"""
import ast
import os

P = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "newton_pick_place",
    "env.py",
)
src = open(P, encoding="utf-8").read()

if "object_assets" in src:
    print("already patched; nothing to do")
    raise SystemExit(0)

# 1) __init__ signature + manifest store
old = """    def __init__(self, cfg: SceneConfig | None = None):
        self.cfg = cfg or SceneConfig()
        # solve the hover home once; the module-level HOME_Q stays as the IK seed
        self.home_q = solve_home_q()"""
new = """    def __init__(self, cfg: SceneConfig | None = None, object_assets: dict[str, str] | None = None):
        self.cfg = cfg or SceneConfig()
        # optional real2sim asset packs: {"bowl": "assets/real2sim/my_bowl", ...}
        # replace the procedural objects (see real2sim.py); None = synthetic
        self.object_assets = dict(object_assets) if object_assets else {}
        self.asset_manifests: dict[str, dict] = {}
        # solve the hover home once; the module-level HOME_Q stays as the IK seed
        self.home_q = solve_home_q()"""
assert old in src, "init anchor missing"
src = src.replace(old, new)

# 2) bowl section: imported pack OR procedural
old = """        # --- bowl: cylinder collision + lathe visual mesh -------------------
        # A concave lathe mesh hull-converted by approximate_meshes welds away
        # the 5 mm bottom ring and rolls off the table; a cylinder primitive
        # gives a flat, stable base while the lathe stays as visual-only mesh.
        bowl_mesh = lathe_mesh(bowl_profile(cfg))
        half_h = cfg.bowl_height / 2.0
        self.bowl_body = builder.add_body(
            xform=wp.transform(wp.vec3(0.45, 0.0, cfg.table_top_z + 0.002), wp.quat_identity()),
            label="bowl",
        )
        idx = builder.add_shape_cylinder(
            body=self.bowl_body,
            radius=cfg.bowl_rim_r,  # collision at the rim radius: the fingers
            # grasp the upper wall, where the taper wedges the bowl on lift
            half_height=half_h,
            xform=wp.transform(wp.vec3(0.0, 0.0, half_h), wp.quat_identity()),
            cfg=contact_cfg(density=cfg.bowl_density, mu=0.8),
        )
        self.shape_roles.setdefault("bowl_collision", []).append(int(idx))
        idx = builder.add_shape_mesh(
            body=self.bowl_body,
            mesh=bowl_mesh,
            cfg=contact_cfg(has_shape_collision=False),  # visual only
        )
        self.shape_roles.setdefault("bowl_visual", []).append(int(idx))"""
new = """        # --- bowl: imported real2sim pack OR cylinder collision + lathe visual
        # (A concave lathe mesh hull-converted by approximate_meshes welds away
        # the 5 mm bottom ring and rolls off the table; a cylinder primitive
        # gives a flat, stable base while the lathe stays as visual-only mesh.)
        half_h = cfg.bowl_height / 2.0
        self.bowl_body = builder.add_body(
            xform=wp.transform(wp.vec3(0.45, 0.0, cfg.table_top_z + 0.002), wp.quat_identity()),
            label="bowl",
        )
        if "bowl" in self.object_assets:
            from real2sim import build_newton_shapes, load_asset_pack

            manifest = load_asset_pack(self.object_assets["bowl"])
            build_newton_shapes(builder, manifest, self.bowl_body, contact_cfg)
            self.asset_manifests["bowl"] = manifest
            n_parts = len(manifest["collision"]["files"])
            self.shape_roles.setdefault("bowl_collision", []).extend(
                range(builder.shape_count - n_parts, builder.shape_count)
            )
            self.shape_roles.setdefault("bowl_visual", []).append(
                builder.shape_count - n_parts - 1
            )
        else:
            bowl_mesh = lathe_mesh(bowl_profile(cfg))
            idx = builder.add_shape_cylinder(
                body=self.bowl_body,
                radius=cfg.bowl_rim_r,  # collision at the rim radius: the fingers
                # grasp the upper wall, where the taper wedges the bowl on lift
                half_height=half_h,
                xform=wp.transform(wp.vec3(0.0, 0.0, half_h), wp.quat_identity()),
                cfg=contact_cfg(density=cfg.bowl_density, mu=0.8),
            )
            self.shape_roles.setdefault("bowl_collision", []).append(int(idx))
            idx = builder.add_shape_mesh(
                body=self.bowl_body,
                mesh=bowl_mesh,
                cfg=contact_cfg(has_shape_collision=False),  # visual only
            )
            self.shape_roles.setdefault("bowl_visual", []).append(int(idx))"""
assert old in src, "bowl section anchor missing"
src = src.replace(old, new)

# 3) cup section: imported pack OR procedural
old = """        # --- cup (vendored newton asset) -----------------------------------
        cup_mesh = load_cup_mesh(cfg)
        self._cup_mesh = cup_mesh  # kept for the studio renderer's OBJ export
        self.cup_zmin = float(cup_mesh.vertices[:, 2].min())
        self.cup_body = builder.add_body(
            xform=wp.transform(wp.vec3(0.45, 0.18, cfg.table_top_z - self.cup_zmin + 0.002), wp.quat_identity()),
            label="cup",
        )
        idx = builder.add_shape_mesh(
            body=self.cup_body,
            mesh=cup_mesh,
            cfg=contact_cfg(density=cfg.cup_density, mu=0.8),
        )
        self.shape_roles.setdefault("cup_collision", []).append(int(idx))"""
new = """        # --- cup: imported real2sim pack OR vendored newton asset -----------
        if "cup" in self.object_assets:
            from real2sim import build_newton_shapes, load_asset_pack

            manifest = load_asset_pack(self.object_assets["cup"])
            self.cup_body = builder.add_body(
                xform=wp.transform(wp.vec3(0.45, 0.18, cfg.table_top_z + 0.002), wp.quat_identity()),
                label="cup",
            )
            build_newton_shapes(builder, manifest, self.cup_body, contact_cfg)
            self.asset_manifests["cup"] = manifest
            n_parts = len(manifest["collision"]["files"])
            self.shape_roles.setdefault("cup_collision", []).extend(
                range(builder.shape_count - n_parts, builder.shape_count)
            )
            self.shape_roles.setdefault("cup_visual", []).append(
                builder.shape_count - n_parts - 1
            )
            self.cup_zmin = 0.0  # pack origin sits at the object's base
        else:
            cup_mesh = load_cup_mesh(cfg)
            self._cup_mesh = cup_mesh  # kept for the studio renderer's OBJ export
            self.cup_zmin = float(cup_mesh.vertices[:, 2].min())
            self.cup_body = builder.add_body(
                xform=wp.transform(
                    wp.vec3(0.45, 0.18, cfg.table_top_z - self.cup_zmin + 0.002), wp.quat_identity()
                ),
                label="cup",
            )
            idx = builder.add_shape_mesh(
                body=self.cup_body,
                mesh=cup_mesh,
                cfg=contact_cfg(density=cfg.cup_density, mu=0.8),
            )
            self.shape_roles.setdefault("cup_collision", []).append(int(idx))"""
assert old in src, "cup section anchor missing"
src = src.replace(old, new)

# 4) reset(): spawn z honors manifest clearance
old = """        joint_q = self.state_0.joint_q.numpy()
        for name, xf in poses.items():
            b = self.object_bodies[name]
            # spawn with the collision shape exactly 2 mm above the surface
            z = cfg.table_top_z + 0.002  # bowl cylinder bottom sits at the body origin
            if name == "cup":
                z = cfg.table_top_z - self.cup_zmin + 0.002  # mesh origin is not its base"""
new = """        joint_q = self.state_0.joint_q.numpy()
        for name, xf in poses.items():
            b = self.object_bodies[name]
            # spawn with the collision shape exactly 2 mm above the surface
            if name in self.asset_manifests:
                z = cfg.table_top_z + float(self.asset_manifests[name].get("spawn_clearance_m", 0.002))
            elif name == "cup":
                z = cfg.table_top_z - self.cup_zmin + 0.002  # mesh origin is not its base
            else:
                z = cfg.table_top_z + 0.002  # bowl cylinder bottom sits at the body origin"""
assert old in src, "reset anchor missing"
src = src.replace(old, new)

open(P, "w", encoding="utf-8").write(src)
ast.parse(src)
print("env.py patched, syntax OK")
