@echo off
REM MEC 2026 tool check - double-click to run (read-only)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-tools.ps1" %*
echo.
pause
