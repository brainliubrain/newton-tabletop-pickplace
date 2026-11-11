        "ms_per_frame_std": round(float(ms.std()), 2),
        "frames_mean": round(float(frames.mean()), 1),
        "agent_ms_per_frame": round(agent_ms, 2),
        "envstep_ms_per_frame": round(envstep_ms, 2),
        "wall_time_s": round(time.time() - t0, 1),
        "per_episode": [
            {
                "seed": r["seed"],
                "outcome": r["outcome"],
                "frames": r["frames"],
                "ms_per_frame": r["ms_per_frame"],
                "agent_ms": r.get("agent_ms_per_frame"),
                "envstep_ms": r.get("envstep_ms_per_frame"),
            }
            for r in records
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--seed-base", type=int, default=0)
    ap.add_argument("--grid", action="append", help="field=v1,v2,... (repeatable)")
    ap.add_argument("--preset", choices=sorted(PRESETS), default=None)
    args = ap.parse_args()

    wp.init()
    task_cfg = TaskConfig()
    configs = grid_from(args)
    print(f"[bench] {len(configs)} config(s) x {args.episodes} episodes, seeds {args.seed_base}..{args.seed_base + args.episodes - 1}")

    results = [eval_config(c, args.episodes, args.seed_base, task_cfg) for c in configs]

    # persist
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, f"bench_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"episodes": args.episodes, "seed_base": args.seed_base, "results": results}, f, indent=2)

    # table
    keys = sorted({k for r in results for k in r["config"]})
    header = ["config"] + keys + ["succ", "rate_ci95", "ms/f", "agent ms", "envstep ms", "frames", "wall_s"]
    print(" | ".join(header))
    print("-" * 100)
    for r in results:
        row = [json.dumps(r["config"], sort_keys=True)]
        row += [str(r["config"].get(k, "-")) for k in keys]
        row += [
            f"{r['successes']}/{r['episodes']}",
            str(r["success_rate_ci95"]),
            f"{r['ms_per_frame_mean']}±{r['ms_per_frame_std']}",
            str(r["agent_ms_per_frame"]),
            str(r["envstep_ms_per_frame"]),
            str(r["frames_mean"]),
            str(r["wall_time_s"]),
        ]
        print(" | ".join(row))
    print(f"[bench] results -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())