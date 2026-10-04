"""Kinematic bicycle-model vehicle simulator.

Produces a ground-truth trajectory (position, heading, speed, and vehicle
body-frame longitudinal/lateral acceleration) for a scripted driving sequence.
This is the reference against which sim/sensor.py generates synthetic raw IMU
data, and against which calibration/calibrate.py's recovered rotation is
scored.
"""
from dataclasses import dataclass
from pathlib import Path
import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


@dataclass
class Segment:
    duration: float   # seconds
    accel: float       # commanded longitudinal accel, m/s^2
    steering: float    # front-wheel steering angle, radians


@dataclass
class Trajectory:
    t: np.ndarray
    x: np.ndarray
    y: np.ndarray
    heading: np.ndarray      # rad, world frame (0 = +x axis)
    speed: np.ndarray        # m/s, forward speed
    yaw_rate: np.ndarray     # rad/s
    accel_long: np.ndarray   # m/s^2, vehicle body-frame forward axis
    accel_lat: np.ndarray    # m/s^2, vehicle body-frame left axis


def simulate(segments, dt=1.0 / 200, wheelbase=2.6, v0=0.0):
    """Integrate a kinematic bicycle model over a sequence of Segments.

    Rear-axle-reference kinematic bicycle model:
        xdot = v*cos(theta), ydot = v*sin(theta)
        thetadot = v/wheelbase * tan(steering)
        vdot = accel
    Under the model's no-sideslip assumption, body-frame acceleration is
    a_long = accel, a_lat = v * thetadot (centripetal term).
    """
    ts, xs, ys, headings, speeds, yaw_rates, a_longs, a_lats = ([] for _ in range(8))
    t, x, y, theta, v = 0.0, 0.0, 0.0, 0.0, v0

    for seg in segments:
        n_steps = max(1, round(seg.duration / dt))
        for _ in range(n_steps):
            thetadot = v / wheelbase * np.tan(seg.steering)
            a_lat = v * thetadot
            # already at rest under braking: no residual decel force, not "reversing"
            a_long = 0.0 if (v <= 0.0 and seg.accel < 0.0) else seg.accel

            ts.append(t); xs.append(x); ys.append(y); headings.append(theta)
            speeds.append(v); yaw_rates.append(thetadot)
            a_longs.append(a_long); a_lats.append(a_lat)

            x += v * np.cos(theta) * dt
            y += v * np.sin(theta) * dt
            theta += thetadot * dt
            v = max(0.0, v + a_long * dt)  # no reverse
            t += dt

    return Trajectory(*(np.array(a) for a in
                         (ts, xs, ys, headings, speeds, yaw_rates, a_longs, a_lats)))


def demo_scenario():
    """Idle, accelerate, cruise, turn left, straight, turn right, straight, brake to stop, idle."""
    return [
        Segment(duration=2.0, accel=0.0, steering=0.0),
        Segment(duration=5.0, accel=2.0, steering=0.0),
        Segment(duration=5.0, accel=0.0, steering=0.0),
        Segment(duration=3.0, accel=0.0, steering=np.radians(8)),
        Segment(duration=4.0, accel=0.0, steering=0.0),
        Segment(duration=3.0, accel=0.0, steering=np.radians(-8)),
        Segment(duration=4.0, accel=0.0, steering=0.0),
        Segment(duration=4.0, accel=-3.0, steering=0.0),
        Segment(duration=2.0, accel=0.0, steering=0.0),
    ]


def straight_line_scenario():
    """Idle, accelerate, cruise, brake to stop, idle -- no turns, lateral accel stays at 0."""
    return [
        Segment(duration=2.0, accel=0.0, steering=0.0),
        Segment(duration=5.0, accel=2.0, steering=0.0),
        Segment(duration=5.0, accel=0.0, steering=0.0),
        Segment(duration=4.0, accel=-3.0, steering=0.0),
        Segment(duration=2.0, accel=0.0, steering=0.0),
    ]


if __name__ == "__main__":
    traj = simulate(demo_scenario())

    assert traj.speed.min() >= 0, "vehicle reversed"
    assert traj.speed.max() > 5, "never got moving"
    assert traj.speed[-1] == 0, "did not come to a stop"
    assert np.isclose(traj.x[0], 0) and np.isclose(traj.y[0], 0)

    print(f"{len(traj.t)} samples over {traj.t[-1]:.1f}s, "
          f"max speed {traj.speed.max():.1f} m/s, "
          f"max |a_lat| {np.abs(traj.accel_lat).max():.2f} m/s^2")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes[0, 0].plot(traj.x, traj.y); axes[0, 0].set_title("path (x, y) [m]"); axes[0, 0].axis("equal")
    axes[0, 1].plot(traj.t, traj.speed); axes[0, 1].set_title("speed [m/s]")
    axes[1, 0].plot(traj.t, traj.accel_long, label="long")
    axes[1, 0].plot(traj.t, traj.accel_lat, label="lat")
    axes[1, 0].set_title("body-frame accel [m/s^2]"); axes[1, 0].legend()
    axes[1, 1].plot(traj.t, np.degrees(traj.heading)); axes[1, 1].set_title("heading [deg]")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "vehicle_sanity_check.png")
    print(f"wrote {RESULTS_DIR / 'vehicle_sanity_check.png'}")
