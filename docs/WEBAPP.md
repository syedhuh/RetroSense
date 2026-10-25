# RetroSense local app

Double-click `Launch_RetroSense_WebApp.bat` in the project root (one folder above this guide). It starts the
local server and opens http://127.0.0.1:8502. Opening it again reuses the running
server. Closing the browser tab does not stop the server.

For a fresh Python installation, run `python -m pip install -r requirements.txt`
once from this folder. For a visible server console, run `python app.py`; press
Ctrl+C in that console to stop it.

Put GNSS Logger `.txt` recordings inside `validation/data/own_drives/` or its
subfolders. Click the refresh button beside Recordings to find newly added logs.

Choose Analyse a drive, select a recording, and click Analyse recording. Compare
two drives accepts two different phones' recordings from the same drive.

The route preserves equal east/north distance scale and points north upward.
Red means slower, amber means intermediate speed, and green means faster,
relative to that recording's displayed speed range.

Use the + / − buttons or scroll the mouse wheel over the route to zoom in and
out. Wheel zoom follows the pointer. Drag to pan, and click Fit drive to restore
the complete route. Keyboard users can focus the route and use + / −, arrow
keys, and 0 (or Home) to reset. Event highlights stay aligned while zooming.

Hover or keyboard-focus an event row to highlight every detected event window
on the motion plot and the corresponding route segments with numbered markers.
Click to pin both views; click again to clear. An event count of zero has no
highlights. Route positions are estimated between timestamped GPS fixes; events
outside GPS coverage or across gaps over five seconds are not mapped.

Raw signals include gravity. The vehicle frame's horizontal signals use the
existing event detector's smoothing; vertical retains gravity. Both frame views
use the same vertical range. Confidence is correlation with GPS-derived motion,
not percentage accuracy. All analysis runs locally on saved recordings.

The app reuses the existing calibration/parser/event scripts. The old Streamlit
interface and its launcher have been removed. Server diagnostics are written to
`results/webapp_server.log` (ignored by Git).
