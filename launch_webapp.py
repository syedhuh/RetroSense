"""Start the local server once, wait until ready, then open the browser."""
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError, HTTPError
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8502"


def ready():
    try:
        with urlopen(URL + "/api/health", timeout=1) as response:
            data = json.load(response)
            return data.get("application") == "RetroSense" and data.get("version") == 2
    except (URLError, HTTPError, ValueError, OSError):
        return False


def main():
    if ready():
        webbrowser.open(URL)
        return 0
    try:
        import flask  # noqa: F401
    except ImportError:
        print("The web app needs Flask. In this project folder run: python -m pip install -r requirements.txt")
        return 1
    log_path = ROOT / "results" / "webapp_server.log"
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("a", encoding="utf-8") as output:
        process = subprocess.Popen([sys.executable, str(ROOT / "app.py")], cwd=ROOT,
                                   stdout=output, stderr=output,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(100):
        if ready():
            webbrowser.open(URL)
            return 0
        if process.poll() is not None:
            print(f"The app could not start. Check {log_path}")
            print("If an older app is running on port 8502, close it and launch again.")
            return 1
        time.sleep(0.2)
    print(f"The app is taking longer to start. Check {log_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
