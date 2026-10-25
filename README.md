# RetroSense: A Self-Calibrating IMU Framework for Vehicle Safety Warnings

RetroSense estimates how a phone is mounted inside a vehicle using recorded
accelerometer, gyroscope, and GPS signals. It maps phone-axis acceleration into
vehicle-forward, lateral, and vertical axes, then reports motion measurements
and harsh braking, acceleration, and cornering events.

The current version analyses saved recordings offline. It does not issue live
driving warnings. Calibration confidence is correlation with GPS-derived motion,
not percentage accuracy or an independent measurement of mounting error.

## Open the web app

Use Python 3.13 with the project's pinned scientific dependencies. From the
project root, install the dependencies once:

```powershell
python -m pip install -r requirements.txt
```

Double-click **Launch_RetroSense_WebApp.bat**. It starts the local Flask server
and opens http://127.0.0.1:8502. Opening the launcher again reuses the running
server. To run with a visible console instead:

```powershell
python app.py
```

Place GNSS Logger `.txt` recordings in `validation/data/own_drives/` or its
subfolders. The app discovers them automatically; click refresh to find new
files. Raw datasets are intentionally excluded from Git, so a fresh clone needs
recordings added locally before real-drive analysis is possible.

The dashboard provides single-drive analysis, independent two-phone calibration
and comparison, raw/vehicle frame plots, route speed colours, event highlights,
and route zoom/pan controls. See the [web app guide](docs/WEBAPP.md) for details.

## Project layout

```text
Retro-Sense-master/
├── app.py                         Flask API and analysis adapter
├── launch_webapp.py               Local server/browser launcher
├── Launch_RetroSense_WebApp.bat    Windows entry point
├── requirements.txt               Python dependencies
├── calibration/
│   └── calibrate.py               Phone-to-vehicle rotation estimation
├── sim/
│   ├── vehicle.py                 Synthetic vehicle trajectory
│   └── sensor.py                  Synthetic IMU with mounting/noise
├── validation/                    Parsers, sweeps and analysis scripts
│   └── data/own_drives/            Local GNSS logs (not committed)
├── templates/index.html           Dashboard structure
├── static/                        Dashboard JavaScript and CSS
├── docs/WEBAPP.md                 Usage and interpretation guide
├── results/
│   ├── comparisons/               Saved two-phone reports
│   ├── dashboard/                 Dashboard preview images
│   ├── paths/                     Saved GPS route plots
│   └── ...                        Simulation/sweep plots and CSV results
├── .agents/skills/                Project-installed design skills
└── skills-lock.json               Sources of installed skills
```

The root keeps launch/configuration files. Core calculations remain in
`calibration/`, synthetic experiments in `sim/`, and validation tools in
`validation/`. Existing result paths are retained so the scripts keep working.

## Validation tools

| File | Purpose |
| --- | --- |
| `validation/gsdc.py` | Parse GNSS Logger data and report estimated mounting |
| `validation/harsh_events.py` | Report calibrated motion peaks and event counts |
| `validation/plot_path.py` | Save a speed-coloured top-down GPS route plot |
| `validation/compare_two_phones.py` | Export a two-phone comparison |
| `validation/sweep.py` | Test calibration over random simulated mounts |
| `validation/gps_rate_sweep.py` | Examine sensitivity to GPS update rate |
| `validation/convergence_sweep.py` | Examine calibration versus driving duration |
| `validation/test_yaw_flip.py` | Evaluate the yaw sign safeguard |
| `validation/real_trips.py` | Evaluate public recorded trips |

These tools can also be run directly from the project root. For example:

```powershell
python validation/gsdc.py "validation/data/own_drives/my_drive.txt"
```

## Reading results

The route is north-up with equal east/north scale. Red means slower and green
means faster within the recording's displayed range. Hover or pin an event row
to locate its time windows and estimated GPS positions. Route markers interpolate
between GPS fixes and omit gaps longer than five seconds.

The accelerometer includes gravity. The vehicle frame's horizontal signals use
the event detector's smoothing, while vertical retains gravity. Comparison of
two phones supports consistency across different mounts; it does not establish
absolute accuracy. Harsh events are threshold counts, without a trip score.

All analysis runs on this computer. Raw recordings, caches, local environments,
and the launcher's diagnostic log are excluded from Git. No cloud service is
required by the dashboard.
