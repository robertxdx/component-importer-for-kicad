@echo off
cd /d "%~dp0"

echo Starting KiCad Component Importer GUI...
echo.

py gui_main.py

if errorlevel 1 (
    echo.
    echo The GUI failed to start.
    echo.
    echo Possible fixes:
    echo 1. Make sure Python is installed.
    echo 2. Install PyQt6 with:
    echo    py -m pip install PyQt6
    echo.
    pause
)