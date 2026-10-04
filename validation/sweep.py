"""Monte Carlo sweep: run the full sim -> IMU -> calibrate pipeline across many
randomized true mounting misalignments, and quantify recovered-vs-true error.

This is the primary quantitative result for the thesis: it shows the
calibration algorithm converges regardless of how the IMU happens to be
glued into the dashboard, not just for one lucky mounting angle.

Writes results/sweep_errors.csv (per-trial table) and
results/sweep_error_plot.png (error distribution).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim.vehicle import simulate, demo_scenario
from sim.sensor import generate, SensorConfig, random_mounting_rotation
from calibration.calibrate import calibrate, rotation_error_deg

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
N_TRIALS = 150


def run_sweep(n_trials=N_TRIALS, seed=0):
    traj = simulate(demo_scenario())
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
        true_roll, true_pitch, true_yaw = true_rotation.as_euler("ZYX", degrees=True)[::-1]

        rows.append(dict(
            trial=trial,
            true_roll_deg=true_roll, true_pitch_deg=true_pitch, true_yaw_deg=true_yaw,
            recovered_roll_deg=result.roll_deg, recovered_pitch_deg=result.pitch_deg,
            recovered_yaw_deg=result.yaw_deg,
            error_deg=rotation_error_deg(result.rotation, true_rotation),
            longitudinal_correlation=result.longitudinal_correlation,
        ))

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run_sweep()
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_DIR / "sweep_errors.csv", index=False)

    err = df["error_deg"]
    print(f"{len(df)} trials: mean={err.mean():.3f} deg, median={err.median():.3f} deg, "
          f"95th pct={err.quantile(0.95):.3f} deg, max={err.max():.3f} deg")
    assert err.median() < 2.0, "calibration median error too large across random mountings"

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].hist(err, bins=30)
    axes[0].axvline(err.median(), color="red", linestyle="--", label=f"median={err.median():.2f} deg")
    axes[0].set_xlabel("total rotation error [deg]")
    axes[0].set_ylabel("trial count")
    axes[0].set_title(f"Calibration error over {len(df)} random mountings")
    axes[0].legend()

    sc = axes[1].scatter(df["true_yaw_deg"], err, c=df["true_roll_deg"], cmap="viridis", s=18)
    axes[1].set_xlabel("true yaw [deg]")
    axes[1].set_ylabel("total rotation error [deg]")
    axes[1].set_title("error vs. true yaw (color = true roll)")
    fig.colorbar(sc, ax=axes[1], label="true roll [deg]")

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "sweep_error_plot.png", dpi=150)
    print(f"wrote {RESULTS_DIR / 'sweep_errors.csv'}")
    print(f"wrote {RESULTS_DIR / 'sweep_error_plot.png'}")
