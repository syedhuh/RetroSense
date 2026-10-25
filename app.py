"""Local RetroSense interface. Start with python app.py or the Windows launcher."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import sys

import numpy as np
from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "validation"))
from gsdc import parse_gnsslog
from harsh_events import analyze, BRAKE, ACCEL, CORNER, MIN_DUR_S, MIN_SPEED
from plot_path import read_fixes

LIBRARY = (ROOT / "validation/data/own_drives").resolve()
app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def confidence_label(value):
    return next(label for threshold, label in [(0.6, "Strong"), (0.35, "Moderate"), (0.15, "Limited"), (-float("inf"), "Weak")] if value >= threshold)


def resolve_log(value):
    path = (LIBRARY / value).resolve()
    if not path.is_relative_to(LIBRARY) or path.suffix.lower() != ".txt" or not path.is_file():
        raise ValueError("Choose a .txt recording from the local recording library.")
    return path


def imu_epoch_ms(path):
    """Match the parser's time origin, independently of the route's GPS provider."""
    columns, earliest = {}, {}
    with path.open(encoding="utf-8", errors="ignore") as stream:
        for line in stream:
            line = line.strip()
            parts = line.lstrip("# ").split(",")
            kind = parts[0]
            if kind not in ("Accel", "UncalAccel"):
                continue
            if line.startswith("#"):
                columns[kind] = parts.index("utcTimeMillis")
            elif kind in columns:
                value = float(parts[columns[kind]])
                if np.isfinite(value):
                    earliest[kind] = min(earliest.get(kind, value), value)
    return earliest["Accel"] if "Accel" in earliest else earliest["UncalAccel"]


@lru_cache(maxsize=8)
def analyse_cached(path_text, modified_ns, size):
    del modified_ns, size
    path = Path(path_text)
    t, acc, gyro, tg, gps_speed, course = parse_gnsslog(path)
    result, events, distance, forward, lateral = analyze(path)
    if not np.isfinite(result.longitudinal_correlation):
        raise ValueError("The recording has too little usable motion to calculate calibration confidence. Choose a drive with stops, acceleration, and turns.")
    vehicle = result.rotation.apply(acc)
    speed = np.interp(t, tg, gps_speed)
    still = speed < 0.3
    if np.any(still):
        vehicle[:, :2] -= vehicle[still, :2].mean(axis=0)

    # Keep the event detector's smoothed horizontal signals, and keep the same
    # gravity-containing vertical convention as the original accelerometer.
    vehicle[:, 0], vehicle[:, 1] = forward, lateral
    step = max(1, int(np.ceil(len(t) / 2200)))
    indices = np.arange(0, len(t), step)
    # Preserve all event peaks and boundaries even when downsampling the graph.
    for windows in events.values():
        for start, end in windows:
            lo, hi = np.searchsorted(t, [start, end])
            event_indices = np.arange(lo, min(hi + 1, len(t)))
            if len(event_indices):
                peaks = [event_indices[np.argmax(np.abs(channel[event_indices]))] for channel in (forward, lateral)]
                indices = np.union1d(indices, [lo, min(hi, len(t) - 1), *peaks])
    indices = np.union1d(indices, [len(t) - 1]).astype(int)
    origin = float(t[0])
    fixes = read_fixes(path).dropna(subset=["UnixTimeMillis"]).sort_values("UnixTimeMillis").drop_duplicates("UnixTimeMillis")
    route_time = (fixes.UnixTimeMillis.to_numpy() - imu_epoch_ms(path)) / 1000.0 - origin
    lat, lon = fixes.LatitudeDegrees.to_numpy(), fixes.LongitudeDegrees.to_numpy()
    x = (lon - lon[0]) * np.cos(np.radians(lat[0])) * 111.32
    y = (lat - lat[0]) * 110.54
    right, top, _ = result.rotation.apply(np.eye(3))
    heading = float(np.degrees(np.arctan2(top[1], top[0])))
    tilt = float(np.degrees(np.arctan2(-top[2], np.hypot(top[0], top[1]))))
    edge = float(np.degrees(np.arcsin(np.clip(right[2], -1, 1))))
    return {
        "log": path.stem, "path": str(path.relative_to(LIBRARY)),
        "durationS": float(t[-1] - t[0]), "distanceKm": float(distance),
        "peakSpeedKmh": float(np.max(gps_speed) * 3.6),
        "confidence": float(result.longitudinal_correlation),
        "confidenceLabel": confidence_label(result.longitudinal_correlation),
        "stationarySamples": result.n_stationary_samples,
        "mounting": {"heading": heading, "tilt": tilt, "edge": edge,
                     "roll": result.roll_deg, "pitch": result.pitch_deg, "yaw": result.yaw_deg},
        "motion": {"forward": float(np.max(forward)), "braking": float(np.min(forward)), "lateral": float(np.max(np.abs(lateral)))},
        "events": {name: len(windows) for name, windows in events.items()},
        "eventWindows": {name: [[float(a - origin), float(b - origin)] for a, b in windows] for name, windows in events.items()},
        "route": [{"x": float(east), "y": float(north), "speed": float(s * 3.6), "time": float(time)} for east, north, s, time in zip(x, y, fixes.SpeedMps, route_time)],
        "signals": {"time": np.round(t[indices] - origin, 4).tolist(),
                    "raw": np.round(acc[indices], 4).tolist(), "vehicle": np.round(vehicle[indices], 4).tolist()},
        "thresholds": {"braking": BRAKE, "acceleration": ACCEL, "cornering": CORNER, "durationS": MIN_DUR_S, "speedMps": MIN_SPEED},
    }


def analyse_log(value):
    path = resolve_log(value)
    stat = path.stat()
    return analyse_cached(str(path), stat.st_mtime_ns, stat.st_size)


def error_response(exc):
    message = str(exc)
    if "stationary samples" in message:
        message = "Not enough still periods to estimate the phone's tilt. Choose a recording with a stationary start or stop."
    elif "moving samples" in message or "estimate yaw" in message:
        message = "Not enough driving motion with usable GPS heading to estimate mounting direction. Choose a drive recording with stops, acceleration, and turns."
    return jsonify({"error": message}), 400


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"application": "RetroSense", "version": 2})


@app.get("/api/logs")
def logs():
    paths = sorted(LIBRARY.rglob("*.txt"), key=lambda p: str(p).lower()) if LIBRARY.exists() else []
    return jsonify({"logs": [{"value": p.relative_to(LIBRARY).as_posix(), "label": str(p.relative_to(LIBRARY))} for p in paths if p.resolve().is_relative_to(LIBRARY)]})


@app.post("/api/analyze")
def analyze_endpoint():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(analyse_log(str(body.get("log", ""))))
    except Exception as exc:
        return error_response(exc)


@app.post("/api/compare")
def compare_endpoint():
    body = request.get_json(silent=True) or {}
    try:
        a_path, b_path = resolve_log(str(body.get("first", ""))), resolve_log(str(body.get("second", "")))
        if a_path == b_path:
            raise ValueError("Choose two different recordings from the same drive.")
        a, b = analyse_log(str(body["first"])), analyse_log(str(body["second"]))
        return jsonify({"first": a, "second": b,
                        "differences": {key: abs(a["motion"][key] - b["motion"][key]) for key in a["motion"]},
                        "eventMatch": a["events"] == b["events"]})
    except Exception as exc:
        return error_response(exc)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8502, debug=False)
