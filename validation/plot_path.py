"""Plot the GPS path of a GNSS Logger trip, colored by speed."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def read_fixes(path):
    cols, rows = None, []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# Fix,"):
                cols = line[2:].split(",")[1:]
            elif line.startswith("Fix,"):
                rows.append(line.split(",")[1:])
    df = pd.DataFrame(rows)
    df.columns = cols[:df.shape[1]]
    if (df["Provider"] == "GPS").any():
        df = df[df["Provider"] == "GPS"]
    for c in df.columns:
        if c != "Provider":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["LatitudeDegrees", "LongitudeDegrees", "SpeedMps"])


if __name__ == "__main__":
    log = Path(sys.argv[1] if len(sys.argv) > 1 else
               Path(__file__).resolve().parent / "data/2020-05-14-US-MTV-2/Pixel4_GnssLog.txt")
    df = read_fixes(log)
    lat, lon = df["LatitudeDegrees"].to_numpy(), df["LongitudeDegrees"].to_numpy()
    x = (lon - lon[0]) * np.cos(np.radians(lat[0])) * 111320   # degrees to meters
    y = (lat - lat[0]) * 110540
    kmh = df["SpeedMps"].to_numpy() * 3.6

    fig, ax = plt.subplots(figsize=(8, 7))
    sc = ax.scatter(x / 1000, y / 1000, c=kmh, s=6, cmap="viridis")
    ax.plot(x[0] / 1000, y[0] / 1000, "go", label="start")
    ax.plot(x[-1] / 1000, y[-1] / 1000, "rs", label="end")
    ax.set_aspect("equal")
    ax.set_xlabel("east [km]")
    ax.set_ylabel("north [km]")
    ax.set_title(f"{log.parent.name} / {log.stem}")
    ax.legend()
    fig.colorbar(sc, label="speed [km/h]")
    out = RESULTS_DIR / f"path_{log.parent.name}_{log.stem}.png"
    RESULTS_DIR.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"wrote {out}")