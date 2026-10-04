# RetroSense

Master's thesis project: a self-calibrating IMU framework for retrofit vehicle
safety warnings in legacy (non-OEM-connected) vehicles, Indian market context.

## Core novelty

Recovering the orientation of an arbitrarily, unknown-mounted consumer IMU
relative to the vehicle body frame, with **no OEM sensor access** — using only:

- IMU (accelerometer + gyroscope)
- GPS (position, velocity, course-over-ground)
- OBD-II speed (via ELM327 dongle)

No physical mounting jig, no manual alignment step by the installer — the
system calibrates itself from normal driving data.

## Coordinate frames

- **IMU frame**: whatever orientation the physical sensor happens to be glued/
  bolted in at (arbitrary roll/pitch/yaw offset from the vehicle). This is the
  frame raw accelerometer/gyro samples are reported in.
- **Vehicle body frame**: x = forward (longitudinal), y = left (lateral),
  z = up. This is the frame the safety-warning logic actually needs
  (forward accel for braking events, lateral accel for cornering, etc).
- **Calibration problem**: recover the fixed rotation `R` such that
  `vehicle_frame_vector = R @ imu_frame_vector`. Represented throughout the
  codebase as a `scipy.spatial.transform.Rotation` object; convert to Euler
  angles (roll/pitch/yaw, intrinsic ZYX) or matrices only at input/output
  boundaries (printing, error metrics, plots). Do not hand-roll rotation
  matrices or compose raw Euler angles elsewhere.

## Current phase: simulation & algorithm validation only

No firmware or embedded code yet. Do not write ESP32/Arduino/C++ code, driver
code for the ICM-20948/NEO-M8N/ELM327, or anything targeting real-time
constraints. Everything here is Python: simulate a vehicle + sensors, run the
calibration algorithm against known ground truth, and validate against real
public GNSS+IMU data (GSDC).

Eventual hardware target (later phase, not now): ESP32 + ICM-20948 IMU +
NEO-M8N GPS + Bluetooth ELM327 OBD-II dongle, logging at 200 Hz.

## Layout

- `sim/` — vehicle + sensor models
  - `vehicle.py` — kinematic bicycle-model simulator producing ground-truth
    trajectory (position, velocity, heading, long./lat. acceleration)
  - `sensor.py` — synthetic raw IMU generator: applies an unknown 3D mounting
    rotation + bias + noise to the vehicle-frame ground truth. True rotation
    is saved alongside the generated data (not embedded in it) for validation.
- `calibration/` — the self-calibration algorithm
  - `calibrate.py` — recovers mounting rotation: roll/pitch from gravity
    alignment (stationary/quasi-static segments), yaw from GPS
    course-over-ground vs. IMU heading under non-holonomic constraints,
    longitudinal axis confirmed by correlating forward accel against
    d(speed)/dt.
- `validation/` — real-data and statistical checks
  - `sweep.py` — Monte Carlo sweep over randomized true misalignments,
    quantifies recovered-vs-true error. Primary quantitative result.
  - `gsdc.py` — runs the same pipeline on real Google Smartphone Decimeter
    Challenge data (dashboard-mounted phone, unknown orientation). Expects
    GSDC CSVs placed under `validation/data/` (gitignored, downloaded
    separately, not committed).
- `results/` — plots and error tables produced by validation scripts.

## Environment

Python venv at `.venv/`. Dependencies: numpy, scipy, matplotlib, pandas
(see `requirements.txt`).
