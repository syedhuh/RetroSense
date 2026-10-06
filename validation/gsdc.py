"""Run the calibration pipeline on real Google Smartphone Decimeter Challenge
(GSDC) data: a dashboard-mounted phone with unknown IMU orientation, real
GNSS position/velocity, and IMU logs. Same calibrate() as the synthetic
pipeline -- only the data-loading adapter differs -- with GPS-derived speed
standing in for the OBD-II leg, same as validation/sweep.py.

There is no ground truth mounting rotation for real data, so this script
only prints the recovered rotation (nothing to score it against).

Expected layout (matches the GSDC 2023 Kaggle release -- adjust the column
alias lists below if your download uses a different year's schema):

    validation/data/<trip_name>/device_imu.csv
    validation/data/<trip_name>/ground_truth.csv   (train trips)
      or  device_gnss.csv                          (test trips, no ground truth)

Download a trip from Kaggle and place it under validation/data/ (gitignored,
not checked into this repo).

device_imu.csv is long-format: one row per sample with a MessageType column
selecting UncalAccel / UncalGyro rows (Android sensor convention: accel in
m/s^2, gyro in rad/s -- already SI, no unit conversion needed).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from calibration.calibrate import calibrate  # noqa: E402 (import after sys.path fix)

DATA_DIR = Path(__file__).resolve().parent / "data"

IMU_TIME_COL = "utcTimeMillis"
IMU_TYPE_COL = "MessageType"
IMU_AXES = ["MeasurementX", "MeasurementY", "MeasurementZ"]
ACCEL_TYPE = "UncalAccel"
GYRO_TYPE = "UncalGyro"

GPS_TIME_ALIASES = ["UnixTimeMillis", "utcTimeMillis"]
GPS_LAT_ALIASES = ["LatitudeDegrees", "latDeg"]
GPS_LON_ALIASES = ["LongitudeDegrees", "lngDeg"]
GPS_SPEED_ALIASES = ["SpeedMps", "speedMps"]
GPS_COURSE_ALIASES = ["BearingDegrees", "HeadingDegrees", "CourseDegrees"]

EARTH_RADIUS_M = 6371000.0


def _pick_column(df, aliases, required=True):
    for name in aliases:
        if name in df.columns:
            return name
    if required:
        raise KeyError(f"none of {aliases} found in columns {list(df.columns)}")
    return None


def load_imu(trip_dir):
    """Return (t_seconds, accel[N,3] m/s^2, gyro[N,3] rad/s) on a common
    timeline, built by nearest-time pairing of the accel and gyro streams."""
    df = pd.read_csv(trip_dir / "device_imu.csv")
    accel = df[df[IMU_TYPE_COL] == ACCEL_TYPE].sort_values(IMU_TIME_COL)
    gyro = df[df[IMU_TYPE_COL] == GYRO_TYPE].sort_values(IMU_TIME_COL)

    merged = pd.merge_asof(
        accel[[IMU_TIME_COL, *IMU_AXES]], gyro[[IMU_TIME_COL, *IMU_AXES]],
        on=IMU_TIME_COL, direction="nearest", suffixes=("_accel", "_gyro"),
    )
    t = (merged[IMU_TIME_COL] - merged[IMU_TIME_COL].iloc[0]).to_numpy() / 1000.0
    accel_arr = merged[[f"{a}_accel" for a in IMU_AXES]].to_numpy(dtype=float)
    gyro_arr = merged[[f"{a}_gyro" for a in IMU_AXES]].to_numpy(dtype=float)
    return t, accel_arr, gyro_arr


def load_gps(trip_dir):
    """Return (t_seconds, speed[N] m/s, course[N] rad) from ground_truth.csv
    (train trips) or device_gnss.csv (test trips). Course/speed are read
    from a bearing/speed column if present, else derived from lat/lon."""
    path = trip_dir / "ground_truth.csv"
    if not path.exists():
        path = trip_dir / "device_gnss.csv"
    df = pd.read_csv(path)

    time_col = _pick_column(df, GPS_TIME_ALIASES)
    lat_col = _pick_column(df, GPS_LAT_ALIASES)
    lon_col = _pick_column(df, GPS_LON_ALIASES)
    speed_col = _pick_column(df, GPS_SPEED_ALIASES, required=False)
    course_col = _pick_column(df, GPS_COURSE_ALIASES, required=False)

    df = df.sort_values(time_col).reset_index(drop=True)
    t = (df[time_col] - df[time_col].iloc[0]).to_numpy(dtype=float) / 1000.0
    lat, lon = np.radians(df[lat_col].to_numpy(dtype=float)), np.radians(df[lon_col].to_numpy(dtype=float))

    if course_col:
        course = np.radians(90.0 - df[course_col].to_numpy(dtype=float))  # compass bearing -> math angle
    else:
        dlat, dlon = np.gradient(lat, t), np.gradient(lon, t) * np.cos(lat.mean())
        course = np.arctan2(dlat, dlon)

    if speed_col:
        speed = df[speed_col].to_numpy(dtype=float)
    else:
        dx = np.gradient(lon, t) * np.cos(lat) * EARTH_RADIUS_M
        dy = np.gradient(lat, t) * EARTH_RADIUS_M
        speed = np.hypot(dx, dy)

    return t, speed, course


def parse_gnsslog(path):
    """Read a GNSS Logger *_GnssLog.txt from a public or personal phone log.

    GNSS Logger can write either calibrated ``Accel``/``Gyro`` records or
    ``UncalAccel``/``UncalGyro`` records.  Prefer calibrated records when a
    phone provides them; otherwise use the uncalibrated stream and let the
    later stationary-period bias removal handle its residual offset.

    Returns (t_imu, accel, gyro, t_gps, speed, course), times in seconds,
    course in radians.
    """
    cols, rows = {}, {
        "Fix": [], "Accel": [], "Gyro": [],
        "UncalAccel": [], "UncalGyro": [],
    }
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            parts = line.lstrip("# ").split(",")
            if parts[0] in rows:
                if line.startswith("#"):
                    cols[parts[0]] = parts[1:]
                else:
                    rows[parts[0]].append(parts[1:])

    def table(kind):
        df = pd.DataFrame(rows[kind])
        df.columns = cols[kind][:df.shape[1]]
        for c in df.columns:
            if c != "Provider":
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    accel_kind = "Accel" if rows["Accel"] else "UncalAccel"
    gyro_kind = "Gyro" if rows["Gyro"] else "UncalGyro"
    if not rows[accel_kind] or not rows[gyro_kind] or not rows["Fix"]:
        raise ValueError("GNSS log needs Fix plus Accel/Gyro or UncalAccel/UncalGyro records")

    acc, gyr, fix = table(accel_kind), table(gyro_kind), table("Fix")
    ts = "utcTimeMillis"

    accel_columns = [f"{accel_kind}XMps2", f"{accel_kind}YMps2", f"{accel_kind}ZMps2"]
    gyro_columns = [f"{gyro_kind}XRadPerSec", f"{gyro_kind}YRadPerSec", f"{gyro_kind}ZRadPerSec"]
    a = acc[[ts, *accel_columns]].set_axis([ts, "ax", "ay", "az"], axis=1).sort_values(ts)
    g = gyr[[ts, *gyro_columns]].set_axis([ts, "gx", "gy", "gz"], axis=1).sort_values(ts)
    m = pd.merge_asof(a, g, on=ts, direction="nearest")

    fix = fix.dropna(subset=["UnixTimeMillis", "SpeedMps", "BearingDegrees"])
    # Some phones write a few sparse raw-GPS fixes plus many more usable FLP
    # (Fused Location Provider) fixes.  Use the provider with the most valid
    # records rather than discarding the denser stream merely because a GPS
    # row exists.
    provider_counts = fix.groupby("Provider").size()
    if not provider_counts.empty:
        fix = fix[fix["Provider"] == provider_counts.idxmax()]
    fix = fix.sort_values("UnixTimeMillis")

    t0 = m[ts].iloc[0]
    t_imu = (m[ts] - t0).to_numpy(dtype=float) / 1000.0
    accel = m[["ax", "ay", "az"]].to_numpy(dtype=float)
    gyro = m[["gx", "gy", "gz"]].to_numpy(dtype=float)
    t_gps = (fix["UnixTimeMillis"] - t0).to_numpy(dtype=float) / 1000.0
    speed = fix["SpeedMps"].to_numpy(dtype=float)
    course = np.radians(90.0 - fix["BearingDegrees"].to_numpy(dtype=float))  # compass bearing to math angle
    return t_imu, accel, gyro, t_gps, speed, course


def _confidence_description(correlation):
    """Return a cautious, presentation-friendly description of correlation."""
    if correlation >= 0.60:
        return "strong"
    if correlation >= 0.35:
        return "moderate"
    if correlation >= 0.15:
        return "limited"
    return "weak"


def print_calibration_summary(log_name, result, duration_s, gps_speed):
    """Print a readable console summary for a demo or review."""
    correlation = result.longitudinal_correlation
    confidence = _confidence_description(correlation)
    max_speed_kmh = float(np.max(gps_speed)) * 3.6
    # Android phone axes: +x = right edge, +y = top edge, +z = out through
    # the screen. Describe the recovered pose as well as the raw Euler values.
    phone_right, phone_top, _screen_normal = result.rotation.apply(np.eye(3))
    top_heading_deg = float(np.degrees(np.arctan2(phone_top[1], phone_top[0])))
    top_downward_deg = float(np.degrees(np.arctan2(
        -phone_top[2], np.hypot(phone_top[0], phone_top[1])
    )))
    right_edge_up_deg = float(np.degrees(np.arcsin(np.clip(phone_right[2], -1.0, 1.0))))
    heading_side = "left" if top_heading_deg >= 0 else "right"
    tilt_direction = "downward" if top_downward_deg >= 0 else "upward"
    edge_direction = "higher" if right_edge_up_deg >= 0 else "lower"

    print("\n=== RetroSense phone calibration ===")
    print(f"Log: {log_name}")
    print(f"Recording analysed: {duration_s:.1f} s | peak GPS speed: {max_speed_kmh:.1f} km/h")
    print("\nStatus: CALIBRATION COMPLETED")
    print(f"Motion-alignment confidence: {correlation:.2f} ({confidence})")
    print("  Higher is better. Values above 0.15 are sufficient for the sign-check safeguard.")
    print("\nEstimated phone mounting:")
    print(f"  Phone top points {abs(top_heading_deg):.1f} degrees {heading_side} of vehicle forward")
    print(f"  Phone top tilts {abs(top_downward_deg):.1f} degrees {tilt_direction}")
    print(f"  Phone right edge is {abs(right_edge_up_deg):.1f} degrees {edge_direction}")
    print("\nTechnical calibration rotation (phone axes to vehicle axes):")
    print(f"  Roll:  {result.roll_deg:7.2f} degrees")
    print(f"  Pitch: {result.pitch_deg:7.2f} degrees")
    print(f"  Yaw:   {result.yaw_deg:7.2f} degrees")
    print(f"\nStationary sensor samples used: {result.n_stationary_samples:,}")
    print()


def run(trip_dir, log_name=None):
    """Load one trip directory or one GNSS Logger text file and calibrate it."""
    source = Path(trip_dir)
    if source.is_file():
        t_imu, accel, gyro, t_gps, gps_speed, gps_course = parse_gnsslog(source)
        trip_name = source.stem
    else:
        logs = sorted(source.glob("*_GnssLog.txt"))
        if log_name:
            logs = [p for p in logs if p.name == log_name]
        if logs:
            t_imu, accel, gyro, t_gps, gps_speed, gps_course = parse_gnsslog(logs[0])
        else:
            t_imu, accel, gyro = load_imu(source)
            t_gps, gps_speed, gps_course = load_gps(source)
        trip_name = source.name

    # GPS is much lower rate than IMU; hold/interpolate onto the IMU timeline
    gps_speed_i = np.interp(t_imu, t_gps, gps_speed)
    gps_course_i = np.interp(t_imu, t_gps, np.unwrap(gps_course))

    # ponytail: stationary/moving thresholds tuned for the sim's clean signals;
    # a real phone accelerometer picks up engine vibration at "rest" -- widen
    # gyro_still_threshold or pre-filter if the stationary leg errors out.
    result = calibrate(t_imu, accel, gyro, gps_speed_i, gps_course_i)
    print_calibration_summary(
        trip_name,
        result,
        duration_s=float(t_imu[-1] - t_imu[0]),
        gps_speed=gps_speed_i,
    )
    return result


def _selftest():
    """Schema smoke test: synthesize a tiny trip matching the documented GSDC
    layout and check the loader/pipeline runs end-to-end without real data."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    try:
        trip = tmp / "toy_trip"
        trip.mkdir()
        n = 500
        t_ms = np.arange(n) * 10 + 1_700_000_000_000  # 100 Hz
        imu_rows = []
        for i in range(n):
            imu_rows.append([t_ms[i], "UncalAccel", 0.1, 0.2, 9.8])
            imu_rows.append([t_ms[i], "UncalGyro", 0.0, 0.0, 0.05])
        pd.DataFrame(imu_rows, columns=[IMU_TIME_COL, IMU_TYPE_COL, *IMU_AXES]).to_csv(
            trip / "device_imu.csv", index=False)

        lat0, lon0 = 12.9716, 77.5946  # Bengaluru, arbitrary
        gt_t_ms = t_ms[::10]
        lat = lat0 + np.linspace(0, 0.001, len(gt_t_ms))
        lon = lon0 + np.linspace(0, 0.001, len(gt_t_ms))
        speed = np.full(len(gt_t_ms), 8.0)
        bearing = np.full(len(gt_t_ms), 45.0)
        pd.DataFrame({
            "UnixTimeMillis": gt_t_ms, "LatitudeDegrees": lat, "LongitudeDegrees": lon,
            "SpeedMps": speed, "BearingDegrees": bearing,
        }).to_csv(trip / "ground_truth.csv", index=False)

        t_imu, accel, gyro = load_imu(trip)
        assert accel.shape == (n, 3) and gyro.shape == (n, 3)
        t_gps, gps_speed, gps_course = load_gps(trip)
        assert len(t_gps) == len(gt_t_ms)
        assert np.allclose(gps_speed, 8.0)

        try:
            run(trip)  # a 100 Hz-uniform toy trip may not satisfy the stationary/moving
        except ValueError:  # gates -- that's fine, this test only checks the parsing path
            pass
        print("gsdc.py self-test passed: schema parsing round-trips correctly")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif len(sys.argv) > 1:
        run(sys.argv[1])
    else:
        trips = sorted(p for p in DATA_DIR.iterdir() if p.is_dir()) if DATA_DIR.exists() else []
        if not trips:
            print(f"No GSDC data found. Download a trip from the Google Smartphone "
                  f"Decimeter Challenge (Kaggle) and place it at:\n"
                  f"  {DATA_DIR}/<trip_name>/device_imu.csv\n"
                  f"  {DATA_DIR}/<trip_name>/ground_truth.csv (or device_gnss.csv)\n"
                  f"Then run: python validation/gsdc.py <trip_dir>\n"
                  f"(or: python validation/gsdc.py --selftest to check the parser alone)")
        else:
            for trip in trips:
                run(trip)
