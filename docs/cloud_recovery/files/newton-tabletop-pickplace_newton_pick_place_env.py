        # same reason). Tray concavity comes from its 5 boxes.
        collide_mesh_shapes = [
            s
            for s in range(builder.shape_count)
            if builder.shape_type[s] == newton.GeoType.MESH
            and (builder.shape_flags[s] & newton.ShapeFlags.COLLIDE_SHAPES)
        ]
        builder.approximate_meshes(
            method="convex_hull", shape_indices=collide_mesh_shapes, keep_visual_shapes=True
        )

        # hull conversion may weld/trim vertices: measure the cup's real
        # collision-hull bottom so reset() can spawn it exactly on surfaces
        self.bowl_zmin = 0.0  # cylinder collision bottom sits at the body origin
        for s, b in enumerate(builder.shape_body):
            if b == self.cup_body and builder.shape_type[s] == newton.GeoType.CONVEX_MESH:
                self.cup_zmin = float(builder.shape_source[s].vertices[:, 2].min())

        ground_idx = builder.add_ground_plane()
        self.shape_roles.setdefault("ground", []).append(int(ground_idx))
        self.model = builder.finalize()

        # spatial indices used by the task / agent
        self.body_names = list(builder.body_label)
        self.hand_idx = HAND_BODY
        self.tcp_idx = TCP_BODY
        self.finger_idx = FINGER_BODIES
        self.bowl_idx = self.bowl_body
        self.cup_idx = self.cup_body
        self.object_bodies = {"bowl": self.bowl_body, "cup": self.cup_body}

        self.solver = newton.solvers.SolverMuJoCo(
            self.model,
            iterations=cfg.solver_iterations,
            ls_iterations=cfg.ls_iterations,
            njmax=cfg.njmax,