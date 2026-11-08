@echo off
REM MEC 2026 setup - double-click to create .venv and install requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause
