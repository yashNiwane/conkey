@echo off
title ConKey - Phonon-2 Voice Setup
cd /d "%~dp0"
echo ========================================================
echo  ConKey real-time voice typing setup (Phonon-2)
echo ========================================================
echo.
python -m pip install --user --disable-pip-version-check fermion-research
if errorlevel 1 goto :fail
echo.
python host\voice_setup.py %*
if errorlevel 1 goto :fail
echo.
pause
exit /b 0

:fail
echo.
echo Voice setup failed. See the message above.
pause
exit /b 1
