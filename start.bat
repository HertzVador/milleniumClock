@echo off
setlocal
cd /d "%~dp0"

rem ---------------------------------------------------------------------------
rem  Location used to fetch sunrise/sunset (night shading on the hour ring).
rem  LAT: latitude  in degrees, -90..90   (positive = North, negative = South)
rem  LON: longitude in degrees, -180..180 (positive = East,  negative = West)
rem  Leave both empty to guess the location from your IP address (ipapi.co).
rem  Times are shown in this computer's time zone, so pick a city in your zone.
rem
rem  Examples:
rem    Paris          48.8566    2.3522
rem    London         51.5074   -0.1278
rem    Reykjavik      64.1466  -21.9426
rem    New York       40.7128  -74.0060
rem    San Francisco  37.7749 -122.4194
rem    Santa Clara    37.3541 -121.9552
rem    Sao Paulo     -23.5505  -46.6333
rem    Cape Town     -33.9249   18.4241
rem    Dubai          25.2048   55.2708
rem    Mumbai         19.0760   72.8777
rem    Tokyo          35.6762  139.6503
rem    Sydney        -33.8688  151.2093
rem ---------------------------------------------------------------------------
set "LAT=37.3541"
set "LON=-121.9552"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv || exit /b 1
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || exit /b 1
)

if defined LAT (
    ".venv\Scripts\python.exe" main.py --lat %LAT% --lon %LON%
) else (
    ".venv\Scripts\python.exe" main.py
)
