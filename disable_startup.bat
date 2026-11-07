@echo off
title Remove ConKey from Windows Startup
cd /d "%~dp0"
python host\startup.py --disable
echo.
pause
