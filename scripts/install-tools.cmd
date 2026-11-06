@echo off
REM MEC 2026 installer - installs only what check-tools marks FAIL; asks first
REM Options: -WithClaudeCode  -WithPostmanCli  -Yes
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-tools.ps1" %*
echo.
pause
