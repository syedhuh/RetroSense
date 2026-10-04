"""GPS-rate sweep: decimate synthetic GPS from 200 Hz down to realistic rates
(zero-order hold between fixes) and measure calibration error and confidence."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim.vehicle import simulate, demo_scenario
from sim.sensor import generate, SensorConfig, random_mounting_rotation
from calibration.calibrate import calibrate, rotation_error_deg

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RATES_HZ = [200, 50, 20, 10, 5, 2, 1]
N_TRIALS = 25
IMU_HZ = 200


def hold(x, stride):
    """Keep every `stride`-th sample and hold it until the next fix."""
    return x[(np.arange(len(x)) // stride) * stride]


def run_sweep(n_trials=N_TRIALS, seed=0):
    traj = simulate(demo_scenario())
    rows = []
    for rate in RATES_HZ:
        stride = IMU_HZ // rate
        master_rng = np.random.default_rng(seed)  # same mountings at every rate
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
            speed = hold(traj.speed + rng.normal(0.0, 0.1, traj.speed.shape), stride)
            course = hold(traj.heading + rng.normal(0.0, np.radians(1.0), traj.heading.shape), stride)
            try:
                r = calibrate(traj.t, imu.accel, imu.gyro, speed, course)
                rows.append(dict(rate_hz=rate, trial=trial, failed=False, 
                                error_deg=rotation_error_deg(r.rotation, true_rot),
                                correlation=r.longitudinal_correlation))
            except ValueError:
                rows.append(dict(rate_hz=rate, trial=trial, failed=True,
                                error_deg=np.nan, correlation=np.nan))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run_sweep()
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_DIR / "gps_rate_sweep.csv", index=False)
    summary = df.groupby("rate_hz", sort=False).agg(
        median_error=("error_deg", "median"),
        median_corr=("correlation", "median"),
        failed=("failed", "sum"),
    )
    print(summary.round(3))