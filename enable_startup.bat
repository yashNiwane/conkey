@echo off
title Register ConKey on Windows Startup
cd /d "%~dp0"
python host\startup.py --enable
if errorlevel 1 (
    echo.
    echo Failed to register ConKey on startup.
    pause
) else (
    echo.
    echo ========================================================
    echo  [SUCCESS] ConKey is now registered on Windows Startup!
    echo  It will run automatically whenever your laptop opens.
    echo ========================================================
    echo.
    pause
)
