"""Create a small, review-friendly comparison from two GNSS Logger drives.

Usage:
    python validation\\compare_two_phones.py "path\\to\\phone_a.txt" "path\\to\\phone_b.txt"

The phones are expected to record the same drive, but may be mounted in
different orientations.  This tool compares transparent summary metrics; it
does not claim that the two devices provide ground-truth mounting angles.
"""
import csv
import sys
from pathlib import Path

import numpy as np

from gsdc import parse_gnsslog
from harsh_events import analyze


RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "comparisons"


def _mounting_summary(rotation):
    """Return human-readable mounting values from a phone-to-vehicle rotation."""
    phone_right, phone_top, _screen_normal = rotation.apply(np.eye(3))
    heading = float(np.degrees(np.arctan2(phone_top[1], phone_top[0])))
    downward = float(np.degrees(np.arctan2(
        -phone_top[2], np.hypot(phone_top[0], phone_top[1])
    )))
    right_edge_up = float(np.degrees(np.arcsin(np.clip(phone_right[2], -1.0, 1.0))))
    return heading, downward, right_edge_up


def summarize(log_path):
    """Run the existing calibration/event pipeline and collect comparable values."""
    t, _acc, _gyro, _tg, speed, _course = parse_gnsslog(log_path)
    result, events, distance_km, long_accel, lat_accel = analyze(log_path)
    heading, downward, right_edge_up = _mounting_summary(result.rotation)
    return {
        "log": Path(log_path).stem,
        "duration_s": float(t[-1] - t[0]),
        "distance_km": float(distance_km),
        "peak_speed_kmh": float(np.max(speed) * 3.6),
        "confidence": float(result.longitudinal_correlation),
        "phone_top_heading_left_deg": heading,
        "phone_top_downward_deg": downward,
        "right_edge_up_deg": right_edge_up,
        "peak_forward_accel_mps2": float(np.max(long_accel)),
        "peak_braking_mps2": float(np.min(long_accel)),
        "peak_lateral_accel_mps2": float(np.max(np.abs(lat_accel))),
        "harsh_brake_count": len(events["harsh_brake"]),
        "harsh_accel_count": len(events["harsh_accel"]),
        "harsh_corner_count": len(events["harsh_corner"]),
    }


def _confidence_label(value):
    if value >= 0.60:
        return "strong"
    if value >= 0.35:
        return "moderate"
    if value >= 0.15:
        return "limited"
    return "weak"


def write_report(rows, output_stem):
    """Write a CSV plus a short Markdown report suitable for a project review."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / f"{output_stem}.csv"
    md_path = RESULTS_DIR / f"{output_stem}.md"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    first, second = rows
    peak_diffs = {
        "forward acceleration": abs(first["peak_forward_accel_mps2"] - second["peak_forward_accel_mps2"]),
        "braking": abs(first["peak_braking_mps2"] - second["peak_braking_mps2"]),
        "lateral acceleration": abs(first["peak_lateral_accel_mps2"] - second["peak_lateral_accel_mps2"]),
    }
    events_match = all(first[k] == second[k] for k in (
        "harsh_brake_count", "harsh_accel_count", "harsh_corner_count"
    ))

    lines = [
        "# RetroSense two-phone comparison",
        "",
        "Both logs were processed independently with the same calibration and event-detection pipeline.",
        "Different mounting estimates are expected because the phones may be physically oriented differently.",
        "",
        "| Metric | " + first["log"] + " | " + second["log"] + " |",
        "|---|---:|---:|",
        f"| Recording duration | {first['duration_s']:.1f} s | {second['duration_s']:.1f} s |",
        f"| Distance estimated from GPS | {first['distance_km']:.2f} km | {second['distance_km']:.2f} km |",
        f"| Peak GPS speed | {first['peak_speed_kmh']:.1f} km/h | {second['peak_speed_kmh']:.1f} km/h |",
        f"| Motion-alignment confidence | {first['confidence']:.2f} ({_confidence_label(first['confidence'])}) | {second['confidence']:.2f} ({_confidence_label(second['confidence'])}) |",
        f"| Phone-top heading, left of forward | {first['phone_top_heading_left_deg']:.1f}° | {second['phone_top_heading_left_deg']:.1f}° |",
        f"| Phone-top tilt, downward | {first['phone_top_downward_deg']:.1f}° | {second['phone_top_downward_deg']:.1f}° |",
        f"| Peak forward acceleration | {first['peak_forward_accel_mps2']:.2f} m/s² | {second['peak_forward_accel_mps2']:.2f} m/s² |",
        f"| Peak braking | {first['peak_braking_mps2']:.2f} m/s² | {second['peak_braking_mps2']:.2f} m/s² |",
        f"| Peak lateral acceleration | {first['peak_lateral_accel_mps2']:.2f} m/s² | {second['peak_lateral_accel_mps2']:.2f} m/s² |",
        f"| Harsh-braking events | {first['harsh_brake_count']} | {second['harsh_brake_count']} |",
        f"| Harsh-acceleration events | {first['harsh_accel_count']} | {second['harsh_accel_count']} |",
        f"| Harsh-cornering events | {first['harsh_corner_count']} | {second['harsh_corner_count']} |",
        "",
        "## Preliminary result",
        "",
        f"The phones produced comparable peak vehicle-motion values: forward acceleration differed by {peak_diffs['forward acceleration']:.2f} m/s², braking by {peak_diffs['braking']:.2f} m/s², and lateral acceleration by {peak_diffs['lateral acceleration']:.2f} m/s².",
        f"The event counts {'matched' if events_match else 'did not fully match'} across the two logs.",
        "",
        "This is evidence that the pipeline can produce similar vehicle-motion summaries from two differently mounted phones on the same drive. It is not yet a ground-truth accuracy measurement; repeat drives will make the conclusion stronger.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, md_path


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python validation\\compare_two_phones.py PHONE_A_LOG PHONE_B_LOG")
    paths = [Path(arg) for arg in sys.argv[1:]]
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"Log file not found: {path}")

    rows = [summarize(path) for path in paths]
    stem = f"{paths[0].stem}_vs_{paths[1].stem}_comparison"
    csv_path, md_path = write_report(rows, stem)
    print("\n=== RetroSense two-phone comparison ===")
    print(f"Logs: {rows[0]['log']} vs {rows[1]['log']}")
    print(f"Confidence: {rows[0]['confidence']:.2f} vs {rows[1]['confidence']:.2f}")
    print("Peak acceleration difference (phone A vs phone B):")
    print(f"  forward:  {abs(rows[0]['peak_forward_accel_mps2'] - rows[1]['peak_forward_accel_mps2']):.2f} m/s^2")
    print(f"  braking:  {abs(rows[0]['peak_braking_mps2'] - rows[1]['peak_braking_mps2']):.2f} m/s^2")
    print(f"  lateral:  {abs(rows[0]['peak_lateral_accel_mps2'] - rows[1]['peak_lateral_accel_mps2']):.2f} m/s^2")
    print(f"Report: {md_path}")
    print(f"Data:   {csv_path}")


if __name__ == "__main__":
    main()
