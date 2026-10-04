"""Targeted regression test for calibrate.py's leg 3 (longitudinal-axis sign
confirmation): does the 180-degree flip branch ever actually fire, and does
it produce a correct result when it does?

validation/sweep.py always drives demo_scenario(), which includes turns --
those give leg 2 (yaw-from-accel-alignment) real lateral/cornering data, so
it may never need correcting. This script instead drives
straight_line_scenario() (no turns, lateral accel stays at 0 throughout)
across randomized mounting rotations, which is the case the docstring claims
leg 3 exists for.

Writes results/yaw_flip_errors.csv and results/yaw_flip_plot.png.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim.vehicle import simulate, straight_line_scenario
from sim.sensor import generate, SensorConfig, random_mounting_rotation
from calibration.calibrate import calibrate, rotation_error_deg

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
N_TRIALS = 80


def run_sweep(n_trials=N_TRIALS, seed=0):
    traj = simulate(straight_line_scenario())
    master_rng = np.random.default_rng(seed)
    rows = []

    for trial in range(n_trials):
        rng = np.random.default_rng(master_rng.integers(0, 2**32 - 1))
        true_rotation = random_mounting_rotation(rng)
        config = SensorConfig(
            mounting_rotation=true_rotation,
            accel_bias=rng.normal(0.0, 0.05, 3),
            gyro_bias=rng.normal(0.0, 0.002, 3),
            seed=int(rng.integers(0, 2**32 - 1)),
        )
        imu = generate(traj, config)
        gps_speed = traj.speed + rng.normal(0.0, 0.1, traj.speed.shape)
        gps_course = traj.heading + rng.normal(0.0, np.radians(1.0), traj.heading.shape)

        result = calibrate(traj.t, imu.accel, imu.gyro, gps_speed, gps_course)
        rows.append(dict(
            trial=trial,
            flipped=result.flipped,
            longitudinal_correlation=result.longitudinal_correlation,
            error_deg=rotation_error_deg(result.rotation, true_rotation),
        ))

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run_sweep()
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_DIR / "yaw_flip_errors.csv", index=False)

    frac_flipped = df["flipped"].mean()
    flipped = df[df["flipped"]]
    not_flipped = df[~df["flipped"]]

    print(f"{len(df)} straight-line trials: {df['flipped'].sum()} flipped ({frac_flipped:.1%})")
    print(f"  flipped     error: mean={flipped['error_deg'].mean():.3f} "
          f"median={flipped['error_deg'].median():.3f} max={flipped['error_deg'].max():.3f} deg"
          if len(flipped) else "  flipped     error: n/a (no trials flipped)")
    print(f"  not flipped error: mean={not_flipped['error_deg'].mean():.3f} "
          f"median={not_flipped['error_deg'].median():.3f} max={not_flipped['error_deg'].max():.3f} deg"
          if len(not_flipped) else "  not flipped error: n/a (all trials flipped)")

    bad_flips = df[(df["flipped"]) & (df["error_deg"] > 2.0)]
    if len(bad_flips):
        print(f"WARNING: {len(bad_flips)} trial(s) flipped but still ended with >2 deg error "
              f"-- flip logic may be buggy, not just under-tested:")
        print(bad_flips)
    else:
        print("no flipped trial exceeded 2 deg error -- flip logic looks correct when it fires")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].hist(not_flipped["error_deg"], bins=20, alpha=0.7, label=f"not flipped (n={len(not_flipped)})")
    axes[0].hist(flipped["error_deg"], bins=20, alpha=0.7, label=f"flipped (n={len(flipped)})")
    axes[0].set_xlabel("total rotation error [deg]")
    axes[0].set_ylabel("trial count")
    axes[0].set_title("Straight-line-only sweep: error by flip status")
    axes[0].legend()

    axes[1].scatter(df["longitudinal_correlation"], df["error_deg"],
                     c=df["flipped"].map({True: "tab:orange", False: "tab:blue"}))
    axes[1].axvline(0, color="gray", linestyle="--")
    axes[1].set_xlabel("longitudinal_correlation (post-flip-decision)")
    axes[1].set_ylabel("total rotation error [deg]")
    axes[1].set_title("orange = flipped, blue = not flipped")

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "yaw_flip_plot.png", dpi=150)
    print(f"wrote {RESULTS_DIR / 'yaw_flip_errors.csv'}")
    print(f"wrote {RESULTS_DIR / 'yaw_flip_plot.png'}")
