@echo off
title ConKey - Laptop Keyboard Remote Server
cd /d "%~dp0"
python host\run_host.py %*
if errorlevel 1 (
    echo.
    echo Server exited with an error.
    pause
)
