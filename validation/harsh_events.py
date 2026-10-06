"""Harsh braking, acceleration, and cornering detector.

The calibrated rotation moves phone acceleration into the vehicle frame:
x = forward and y = left.
"""
import sys
from pathlib import Path
import numpy as np
from scipy.ndimage import uniform_filter1d

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gsdc import parse_gnsslog
from calibration.calibrate import calibrate

BRAKE, ACCEL, CORNER = 3.0, 3.0, 3.0   # m/s^2 thresholds
MIN_DUR_S = 0.5                         # event must last at least this long
MIN_SPEED = 2.0                         # m/s, ignore events when nearly stopped


def find_events(mask, t, min_dur):
    edges = np.diff(mask.astype(int), prepend=0, append=0)
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    return [(t[s], t[e - 1]) for s, e in zip(starts, ends) if t[e - 1] - t[s] >= min_dur]


def analyze(log_path):
    t, acc, gyro, tg, sp, co = parse_gnsslog(log_path)
    speed = np.interp(t, tg, sp)
    course = np.interp(t, tg, np.unwrap(co))
    res = calibrate(t, acc, gyro, speed, course)

    v = res.rotation.apply(acc)                 # vehicle frame
    still = speed < 0.3
    v[:, :2] -= v[still, :2].mean(axis=0)       # remove residual sensor bias
    w = max(1, int(0.5 / np.median(np.diff(t))))  # about 0.5 s smoothing
    a_long, a_lat = uniform_filter1d(v[:, 0], w), uniform_filter1d(v[:, 1], w)
    moving = speed > MIN_SPEED

    ev = {
        "harsh_brake": find_events((a_long < -BRAKE) & moving, t, MIN_DUR_S),
        "harsh_accel": find_events((a_long > ACCEL) & moving, t, MIN_DUR_S),
        "harsh_corner": find_events((np.abs(a_lat) > CORNER) & moving, t, MIN_DUR_S),
    }
    km = float(np.sum(speed[:-1] * np.diff(t))) / 1000.0
    return res, ev, km, a_long, a_lat


if __name__ == "__main__":
    log = Path(sys.argv[1] if len(sys.argv) > 1 else
               Path(__file__).resolve().parent / "data/2020-05-14-US-MTV-2/Pixel4_GnssLog.txt")
    res, ev, km, a_long, a_lat = analyze(log)
    print(f"{log.name}: {km:.1f} km, calibration corr {res.longitudinal_correlation:.2f}")
    print(f"peak fwd accel {a_long.max():.2f}, peak braking {a_long.min():.2f}, "
          f"peak lateral {np.abs(a_lat).max():.2f} m/s^2")
    for name, e in ev.items():
        print(f"  {name}: {len(e)}")
