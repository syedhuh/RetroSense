"""Plot the route from any GNSS Logger text log, colored by speed."""
import re
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "paths"


def read_fixes(path):
    """Read valid ``Fix`` records from a standard GNSS Logger text file.

    Phones can mix sparse raw-GPS records with denser FLP (fused-location)
    records.  Selecting the provider with the most complete fixes gives a
    usable route for either style of phone log.
    """
    cols, rows = None, []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# Fix,"):
                cols = line[2:].split(",")[1:]
            elif line.startswith("Fix,"):
                rows.append(line.split(",")[1:])
    if cols is None or not rows:
        raise ValueError(f"No GNSS Logger Fix records found in {path}")

    df = pd.DataFrame(rows)
    df.columns = cols[:df.shape[1]]
    for c in df.columns:
        if c != "Provider":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["LatitudeDegrees", "LongitudeDegrees", "SpeedMps"])
    if df.empty:
        raise ValueError(f"No complete latitude, longitude, and speed fixes found in {path}")

    provider_counts = df.groupby("Provider").size()
    provider = provider_counts.idxmax()
    return df[df["Provider"] == provider].copy()


if __name__ == "__main__":
    log = Path(sys.argv[1] if len(sys.argv) > 1 else
               Path(__file__).resolve().parent / "data/2020-05-14-US-MTV-2/Pixel4_GnssLog.txt")
    df = read_fixes(log)
    lat, lon = df["LatitudeDegrees"].to_numpy(), df["LongitudeDegrees"].to_numpy()
    x = (lon - lon[0]) * np.cos(np.radians(lat[0])) * 111320   # degrees to meters
    y = (lat - lat[0]) * 110540
    kmh = df["SpeedMps"].to_numpy() * 3.6

    x_km, y_km = x / 1000, y / 1000
    fig, ax = plt.subplots(figsize=(8, 7))

    # Colour each route segment by its GPS speed.  Small, faint dots remain
    # visible so the plot still shows that the route comes from discrete fixes.
    points = np.column_stack((x_km, y_km)).reshape(-1, 1, 2)
    segments = np.concatenate((points[:-1], points[1:]), axis=1)
    norm = Normalize(vmin=float(kmh.min()), vmax=float(kmh.max()))
    route = LineCollection(segments, cmap="RdYlGn", norm=norm, linewidth=2.0)
    route.set_array((kmh[:-1] + kmh[1:]) / 2.0)
    ax.add_collection(route)
    ax.scatter(x_km, y_km, c=kmh, s=8, cmap="RdYlGn", norm=norm,
               alpha=0.55, edgecolors="none", label="GPS fixes")
    ax.plot(x[0] / 1000, y[0] / 1000, "go", label="start")
    ax.plot(x[-1] / 1000, y[-1] / 1000, "rs", label="end")
    ax.set_aspect("equal")
    ax.set_xlabel("east [km]")
    ax.set_ylabel("north [km]")
    ax.set_title(log.stem)
    ax.legend()
    fig.colorbar(route, ax=ax, label="speed [km/h]")
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", log.stem).strip("_")
    out = RESULTS_DIR / f"{safe_stem}_path.png"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"wrote {out} ({len(df)} fixes from {df['Provider'].iloc[0]})")
