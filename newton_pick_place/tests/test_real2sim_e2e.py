"""End-to-end test of the real2sim pipeline (no real hardware needed).

1. Export a synthetic 'scan' OBJ (the procedural bowl profile, real-world-ish
   size) — stand-in for a photogrammetry capture.
2. Run the real2sim CLI import -> asset pack with CoACD decomposition.
3. Load the pack into PickPlaceEnv via object_assets and step an episode:
   the imported bowl must spawn, settle on the table, and be graspable space.
4. Contract-test the sim2real layer: DeploymentRunner over NewtonSimBackend
   and MockArmBackend.

Run: .venv/Scripts/python.exe tests/test_real2sim_e2e.py
"""

import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
wp.init()

from env import PickPlaceEnv, SceneConfig, bowl_profile, lathe_mesh  # noqa: E402
import real2sim  # noqa: E402
from agent import PickPlaceAgent  # noqa: E402
from task import EpisodeJudge, TaskConfig  # noqa: E402
from sim2real import (  # noqa: E402
    DeploymentRunner,
    MockArmBackend,
    NewtonSimBackend,
)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def test_import_pipeline() -> str:
    mesh = lathe_mesh(bowl_profile(SceneConfig()), segments=48)
    scan_path = os.path.join(TESTS_DIR, "synthetic_scan_bowl.obj")
    import trimesh

    tm = trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices, dtype=np.float64),
        faces=np.asarray(mesh.indices, dtype=np.int64).reshape(-1, 3),
    )
    tm.export(scan_path)
    print(f"[1] synthetic scan exported: {scan_path}")

    pack = real2sim.import_object(
        name="test_bowl",
        mesh_path=scan_path,
        mass_kg=0.25,
        category="bowl",
        collision_mode="decomp",
    )
    manifest = real2sim.load_asset_pack(pack)
    assert manifest["collision"]["mode"] == "decomp", "CoACD decomposition expected"
    assert manifest["collision"]["parts"] >= 2, "a hollow bowl should decompose into >=2 parts"
    assert abs(manifest["mass_kg"] - 0.25) < 1e-6
    print(f"[2] asset pack OK: {manifest['collision']['parts']} convex parts")
    return pack


def test_env_with_imported_bowl(pack: str):
    env = PickPlaceEnv(object_assets={"bowl": pack})
    poses = env.reset(seed=0)
    hold = np.asarray(env.home_q, dtype=np.float32)
    for _ in range(90):
        env.step(hold)
    q = env.body_poses()
    b = env.object_bodies["bowl"]
    assert np.all(np.isfinite(q)), "NaN in body_q with imported asset"
    assert 0.36 < q[b, 2] < 0.46, f"imported bowl did not settle on the table: z={q[b, 2]}"
    print(f"[3] env with imported bowl OK: settles at z={q[b, 2]:.3f}")
    return env


def test_sim2real_contract(env):
    agent = PickPlaceAgent(env)
    poses = env.reset(seed=0)
    agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})

    backend = NewtonSimBackend(env)
    runner = DeploymentRunner(backend, agent, max_frames=120)
    result = runner.run()
    assert result["frames"] == 120, f"runner drove {result['frames']} frames"
    state = backend.get_state()
    assert state["joint_q"].shape == (9,)
    print(f"[4] NewtonSimBackend contract OK ({result['frames']} frames, no violations={not result['violations']})")

    mock = MockArmBackend()
    runner2 = DeploymentRunner(mock, agent, max_frames=60)
    result2 = runner2.run()
    assert result2["frames"] == 60
    print("[5] MockArmBackend contract OK")


if __name__ == "__main__":
    pack = test_import_pipeline()
    env = test_env_with_imported_bowl(pack)
    test_sim2real_contract(env)
    print("REAL2SIM/SIM2REAL E2E: ALL PASS")
