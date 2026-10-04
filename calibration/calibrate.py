"""Self-calibration algorithm: recovers the IMU-to-vehicle mounting rotation.

Three legs, each observing a different part of the rotation:
1. Roll & pitch -- from the gravity direction measured during
    stationary/quasi-static segments (GPS speed ~ 0). Yaw is unobservable
    from gravity alone.
2. Yaw -- from aligning the leveled (roll/pitch-corrected) horizontal
    accelerometer vector against the vehicle-frame (forward, lateral) accel
    implied by GPS: forward = d(speed)/dt, lateral = speed * d(course)/dt
    (the non-holonomic assumption that body-frame lateral velocity is ~0,
    so all cornering shows up as centripetal accel, none as sideslip).
    Note a *gyro* z-rate cannot be used for this leg: once leveled, a
    z-axis gyro reads the true yaw rate regardless of yaw mounting offset
    (rotation about an axis never changes that axis's own reading), so it
    carries no information about yaw misalignment. Only the horizontal
    accelerometer axes -- which really do get relabeled by yaw -- can.
3. Longitudinal-axis sign confirmation -- correlate the recovered forward
    axis's accelerometer reading against d(speed)/dt (OBD-II proxy: GPS
    speed for now). A clearly negative correlation (below -flip_confidence) 
    means the yaw leg locked onto the reverse heading; flip 180 degrees.
    In practice leg 2 never actually needs this correcting (verified via
    validation/test_yaw_flip.py: 0/80 straight-line-only trials flip, same
    as the turning-scenario sweep) -- its complex-correlation fit already
    resolves the full signed yaw against d(speed)/dt, which is itself
    signed (positive under acceleration, negative under braking), so
    there's no leftover mod-180 ambiguity for leg 3 to catch, with or
    without cornering data. A real axis-only estimator (e.g. PCA on the
    horizontal accel covariance) would have that ambiguity; this one
    doesn't. Kept as a defensive check anyway -- confirmed the flip
    mechanism itself is correct by forcing a deliberately-180-off rotation
    and checking the correlation sign flips accordingly -- since real GSDC
    data (GPS dropout, low-satellite-count course glitches, engine
    vibration) could plausibly overwhelm leg 2 in ways the clean sim never
    does.

Works on plain arrays (t, accel, gyro, gps speed/course) so the same function
serves both the synthetic pipeline (validation/sweep.py) and real GSDC data
(validation/gsdc.py).
"""
from dataclasses import dataclass
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.signal import savgol_filter


@dataclass
class CalibrationResult:
    rotation: Rotation   # recovered rotation: vehicle_vector = rotation.apply(imu_vector)
    roll_deg: float
    pitch_deg: float
    yaw_deg: float
    n_stationary_samples: int
    longitudinal_correlation: float
    flipped: bool  # True if leg 3 actually reversed the leg-2 yaw estimate 180 degrees


def _roll_pitch_from_gravity(accel_imu, stationary_mask):
    if stationary_mask.sum() < 10:
        raise ValueError("not enough stationary samples to estimate gravity direction")
    g_imu = accel_imu[stationary_mask].mean(axis=0)
    g_imu_hat = g_imu / np.linalg.norm(g_imu)
    # minimal (no added yaw) rotation aligning measured gravity to vehicle "up"
    r_rp, _ = Rotation.align_vectors([[0, 0, 1]], [g_imu_hat])
    return r_rp


def _smoothed_derivative(x, t, window=51, polyorder=2):
    """d/dt via Savitzky-Golay, not plain finite differences: naive np.gradient
    on a noisy, 200 Hz-oversampled GPS signal amplifies noise by ~1/dt, which
    swamps the ~2-3 m/s^2 accel/brake signal it's meant to expose."""
    dt = t[1] - t[0]
    return savgol_filter(x, window, polyorder, deriv=1, delta=dt)


def _yaw_from_accel_alignment(t, accel_imu, r_rp, gps_speed, gps_course, forward_gps, moving_mask):
    if moving_mask.sum() < 10:
        raise ValueError("not enough moving samples with valid GPS course to estimate yaw")
    measured = r_rp.apply(accel_imu)[:, :2]  # leveled, but horizontal axes still yaw-rotated

    course_rate = _smoothed_derivative(np.unwrap(gps_course), t)
    lateral_gps = gps_speed * course_rate  # non-holonomic: all cornering is centripetal accel

    m = measured[moving_mask, 0] + 1j * measured[moving_mask, 1]
    truth = forward_gps[moving_mask] + 1j * lateral_gps[moving_mask]
    # measured = rot(-yaw) * truth  =>  yaw = angle(sum(truth * conj(measured)))
    yaw_offset = float(np.angle(np.sum(truth * np.conj(m))))
    return yaw_offset


def _longitudinal_correlation(accel_imu, rotation, forward_gps, moving_mask):
    forward_accel = rotation.apply(accel_imu)[:, 0]
    return np.corrcoef(forward_accel[moving_mask], forward_gps[moving_mask])[0, 1]


def calibrate(t, accel_imu, gyro_imu, gps_speed, gps_course, stationary_threshold=0.3, 
            moving_threshold=1.0, gyro_still_threshold=0.05, flip_confidence=0.15, 
            min_duration_s=5.0):
    """Recover the rotation R such that vehicle_vector = R.apply(imu_vector)."""
    # quasi-static: not moving by GPS, and not rotating either (gyro is mounting-
    # orientation-agnostic in magnitude, so it needs no calibration to use here)
        # too little driving: leg 3 has nothing to check against, result untrustworthy
    duration = (t[-1] - t[0]) + (t[1] - t[0])
    if duration < min_duration_s - 1e-6:
        raise ValueError(f"only {duration:.1f}s of data, need at least {min_duration_s}s")
    stationary = (gps_speed < stationary_threshold) & (np.linalg.norm(gyro_imu, axis=1) < gyro_still_threshold)
    moving = gps_speed > moving_threshold
    forward_gps = _smoothed_derivative(gps_speed, t)

    r_rp = _roll_pitch_from_gravity(accel_imu, stationary)
    yaw_offset = _yaw_from_accel_alignment(t, accel_imu, r_rp, gps_speed, gps_course, forward_gps, moving)
    rotation = Rotation.from_euler("z", yaw_offset) * r_rp

    corr = _longitudinal_correlation(accel_imu, rotation, forward_gps, moving)
    flipped = corr < -flip_confidence
    if flipped:
        rotation = Rotation.from_euler("z", np.pi) * rotation
        corr = _longitudinal_correlation(accel_imu, rotation, forward_gps, moving)

    yaw, pitch, roll = rotation.as_euler("ZYX", degrees=True)
    return CalibrationResult(rotation, roll, pitch, yaw, int(stationary.sum()), float(corr), flipped)


def rotation_error_deg(recovered: Rotation, true: Rotation) -> float:
    """Total angular error between two rotations, in degrees (wraparound-safe)."""
    return (recovered.inv() * true).magnitude() * 180.0 / np.pi


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sim.vehicle import simulate, demo_scenario
    from sim.sensor import generate, SensorConfig, random_mounting_rotation

    traj = simulate(demo_scenario())
    rng = np.random.default_rng(7)
    true_rotation = random_mounting_rotation(rng)
    imu = generate(traj, SensorConfig(
        mounting_rotation=true_rotation,
        accel_bias=np.array([0.05, -0.03, 0.04]),
        gyro_bias=np.array([0.001, -0.0015, 0.002]),
        seed=7,
    ))

    # synthetic GPS, derived straight from ground truth at IMU sample rate.
    # ponytail: real GPS is ~10 Hz with its own noise model; here it's an
    # idealized same-rate signal. Upgrade with decimation + interpolation
    # once real GPS timing/dropout matters.
    gps_speed = traj.speed + rng.normal(0, 0.1, traj.speed.shape)
    gps_course = traj.heading + rng.normal(0, np.radians(1.0), traj.heading.shape)

    result = calibrate(traj.t, imu.accel, imu.gyro, gps_speed, gps_course)

    true_roll, true_pitch, true_yaw = true_rotation.as_euler("ZYX", degrees=True)[::-1]
    print(f"true      roll={true_roll:7.2f} pitch={true_pitch:7.2f} yaw={true_yaw:7.2f}")
    print(f"recovered roll={result.roll_deg:7.2f} pitch={result.pitch_deg:7.2f} yaw={result.yaw_deg:7.2f}")

    error_deg = rotation_error_deg(result.rotation, true_rotation)
    print(f"total rotation error: {error_deg:.2f} deg  "
          f"(stationary samples: {result.n_stationary_samples}, "
          f"longitudinal-axis correlation: {result.longitudinal_correlation:.2f})")
    assert error_deg < 5.0, "calibration error too large"
