"""Copy a few public GSDC trips (GnssLog files only) and run calibrate() on every phone log."""
import shutil, sys
from pathlib import Path
import kagglehub

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gsdc import run, DATA_DIR

TRIPS = ["2020-05-14-US-MTV-1", "2020-05-21-US-MTV-1", "2020-05-29-US-MTV-1"]

src = Path(kagglehub.dataset_download("google/android-smartphones-high-accuracy-datasets"))
for name in TRIPS:
    folder = next(src.rglob(name))
    dest = DATA_DIR / name
    dest.mkdir(parents=True, exist_ok=True)
    for log in folder.glob("*_GnssLog.txt"):
        shutil.copy(log, dest / log.name)
        try:
            print(log.name, end=" -> ")
            run(dest, log.name)
        except Exception as e:
            print(f"failed: {e}")