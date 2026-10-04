"""Synthetic raw IMU generator.

Takes a vehicle-frame ground-truth Trajectory (sim/vehicle.py) and produces
raw accelerometer/gyroscope samples as an arbitrarily-mounted IMU would
report them: vehicle-frame motion rotated into the IMU frame by an unknown
mounting rotation, plus bias and Gaussian noise.

The true mounting rotation is the thing calibration/calibrate.py has to
recover. It is returned by the caller's own SensorConfig, not embedded in
ImuData, so the calibration algorithm never has access to it -- it is only
used afterwards, by validation code, to score the recovered rotation.
"""
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

GRAVITY = 9.81


@dataclass
class SensorConfig:
    mounting_rotation: Rotation  # true rotation: v_vehicle = mounting_rotation.apply(v_imu)
    accel_bias: np.ndarray = field(default_factory=lambda: np.zeros(3))   # m/s^2, IMU frame
    gyro_bias: np.ndarray = field(default_factory=lambda: np.zeros(3))    # rad/s, IMU frame
    accel_noise_std: float = 0.05   # m/s^2
    gyro_noise_std: float = 0.01    # rad/s
    seed: int | None = None


@dataclass
class ImuData:
    t: np.ndarray
    accel: np.ndarray  # (N, 3) raw IMU-frame accelerometer, m/s^2
    gyro: np.ndarray   # (N, 3) raw IMU-frame gyro, rad/s


def random_mounting_rotation(rng, max_roll_deg=30.0, max_pitch_deg=30.0, max_yaw_deg=180.0):
    """A plausible retrofit mounting misalignment: bounded roll/pitch, arbitrary yaw."""
    roll = rng.uniform(-max_roll_deg, max_roll_deg)
    pitch = rng.uniform(-max_pitch_deg, max_pitch_deg)
    yaw = rng.uniform(-max_yaw_deg, max_yaw_deg)
    return Rotation.from_euler("ZYX", [yaw, pitch, roll], degrees=True)


def generate(traj, config: SensorConfig) -> ImuData:
    """Simulate raw IMU output for `traj` as measured by a mounted-at-`config` sensor."""
    n = len(traj.t)
    accel_vehicle = np.column_stack([traj.accel_long, traj.accel_lat, np.zeros(n)])
    accel_vehicle[:, 2] += GRAVITY  # specific force = accel - gravity(0,0,-g); flat-ground assumption
    gyro_vehicle = np.column_stack([np.zeros(n), np.zeros(n), traj.yaw_rate])

    imu_from_vehicle = config.mounting_rotation.inv()
    accel_imu = imu_from_vehicle.apply(accel_vehicle)
    gyro_imu = imu_from_vehicle.apply(gyro_vehicle)

    rng = np.random.default_rng(config.seed)
    accel_imu += config.accel_bias + rng.normal(0.0, config.accel_noise_std, accel_imu.shape)
    gyro_imu += config.gyro_bias + rng.normal(0.0, config.gyro_noise_std, gyro_imu.shape)

    return ImuData(t=traj.t, accel=accel_imu, gyro=gyro_imu)


if __name__ == "__main__":
    from vehicle import simulate, demo_scenario

    traj = simulate(demo_scenario())
    rng = np.random.default_rng(42)
    true_rotation = random_mounting_rotation(rng)
    config = SensorConfig(
        mounting_rotation=true_rotation,
        accel_bias=np.array([0.1, -0.05, 0.08]),
        gyro_bias=np.array([0.002, -0.001, 0.003]),
        seed=42,
    )
    imu = generate(traj, config)

    print("true mounting rotation (roll, pitch, yaw deg):",
          true_rotation.as_euler("ZYX", degrees=True)[::-1])

    # sanity check: rotation preserves vector magnitude, so accel norm during the
    # opening stationary segment should still read ~1g regardless of mounting.
    stationary_norm = np.linalg.norm(imu.accel[:300], axis=1).mean()
    print(f"mean |accel| during stationary segment: {stationary_norm:.3f} m/s^2 (expect ~{GRAVITY})")
    assert abs(stationary_norm - GRAVITY) < 0.2, "gravity magnitude not preserved by rotation"

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(imu.t, imu.accel)
    axes[0].set_title("raw IMU-frame accelerometer [m/s^2]")
    axes[0].legend(["x", "y", "z"])
    axes[1].plot(imu.t, imu.gyro)
    axes[1].set_title("raw IMU-frame gyro [rad/s]")
    axes[1].legend(["x", "y", "z"])
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "sensor_sanity_check.png")
    print(f"wrote {RESULTS_DIR / 'sensor_sanity_check.png'}")
