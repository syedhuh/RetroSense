"""Convergence sweep: feed calibrate() a growing time-prefix of the drive
(3 s to 32 s) to see how much driving it needs before the result is trusted."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim.vehicle import simulate, demo_scenario
from sim.sensor import generate, SensorConfig, random_mounting_rotation
from calibration.calibrate import calibrate, rotation_error_deg

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
DURATIONS_S = [3, 4, 5, 6, 8, 10, 12, 15, 18, 22, 26, 29, 32]
N_TRIALS = 40
IMU_HZ = 200


def run_sweep(n_trials=N_TRIALS, seed=0):
    traj = simulate(demo_scenario())
    master_rng = np.random.default_rng(seed)
    rows = []
    for trial in range(n_trials):
        rng = np.random.default_rng(master_rng.integers(0, 2**32 - 1))
        true_rot = random_mounting_rotation(rng)
        cfg = SensorConfig(
            mounting_rotation=true_rot,
            accel_bias=rng.normal(0.0, 0.05, 3),
            gyro_bias=rng.normal(0.0, 0.002, 3),
            seed=int(rng.integers(0, 2**32 - 1)),
        )
        imu = generate(traj, cfg)
        speed = traj.speed + rng.normal(0.0, 0.1, traj.speed.shape)
        course = traj.heading + rng.normal(0.0, np.radians(1.0), traj.heading.shape)

        for dur in DURATIONS_S:
            n = min(int(dur * IMU_HZ), len(traj.t))
            try:
                r = calibrate(traj.t[:n], imu.accel[:n], imu.gyro[:n], speed[:n], course[:n])
                rows.append(dict(duration_s=dur, trial=trial, failed=False,
                                error_deg=rotation_error_deg(r.rotation, true_rot),
                                flipped=r.flipped))
            except ValueError:
                rows.append(dict(duration_s=dur, trial=trial, failed=True,
                                error_deg=np.nan, flipped=False))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run_sweep()
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_DIR / "convergence_sweep.csv", index=False)
    summary = df.groupby("duration_s").agg(
        median_error=("error_deg", "median"),
        max_error=("error_deg", "max"),
        pct_under_1deg=("error_deg", lambda x: 100 * (x < 1.0).mean()),
        flips=("flipped", "sum"),
        failed=("failed", "sum"),
    )
    print(summary.round(2))