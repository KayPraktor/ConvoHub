@echo off
rem Start ConvoHub from source (with a console window). It opens in your browser at http://127.0.0.1:28765
rem Prefer the desktop shortcut that install.bat creates (no console window).
chcp 65001 >nul
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is not installed. Run install.bat first.
    pause
    exit /b 1
)

uv run --no-dev python -m convohub
pause
