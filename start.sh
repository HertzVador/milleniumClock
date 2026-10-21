#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"

# -----------------------------------------------------------------------------
# Location used to fetch sunrise/sunset (night shading on the hour ring).
# LAT: latitude  in degrees, -90..90   (positive = North, negative = South)
# LON: longitude in degrees, -180..180 (positive = East,  negative = West)
# Leave both empty to guess the location from your IP address (ipapi.co).
# Times are shown in this computer's time zone, so pick a city in your zone.
#
# Examples:
#   Paris          48.8566    2.3522
#   London         51.5074   -0.1278
#   Reykjavik      64.1466  -21.9426
#   New York       40.7128  -74.0060
#   San Francisco  37.7749 -122.4194
#   Sao Paulo     -23.5505  -46.6333
#   Cape Town     -33.9249   18.4241
#   Dubai          25.2048   55.2708
#   Mumbai         19.0760   72.8777
#   Tokyo          35.6762  139.6503
#   Sydney        -33.8688  151.2093
# -----------------------------------------------------------------------------
LAT="48.8566"
LON="2.3522"

if [ ! -x .venv/bin/python ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
fi

if [ -n "$LAT" ]; then
    exec .venv/bin/python main.py --lat "$LAT" --lon "$LON"
else
    exec .venv/bin/python main.py
fi
