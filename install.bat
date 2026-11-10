@echo off
rem ConvoHub - install from source (needs uv: https://docs.astral.sh/uv/).
rem Run once after downloading/cloning. It installs Python packages into .venv and puts
rem "ConvoHub" and "ConvoHub - stop" shortcuts on your desktop. Nothing outside this folder
rem changes except those two shortcuts.
chcp 65001 >nul
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo [!] uv is not installed.
    echo     Install it with this command in PowerShell, then run install.bat again:
    echo     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    pause
    exit /b 1
)

echo Installing Python and packages (first time can take a few minutes)...
uv sync --no-dev
if errorlevel 1 (
    echo [!] Installing packages failed. See the messages above.
    pause
    exit /b 1
)

echo Creating desktop shortcuts...
uv run --no-dev python -m convohub.shortcut
if errorlevel 1 (
    echo [!] Could not create the shortcuts. You can still start ConvoHub with start.bat
)

echo.
echo Done. Double-click "ConvoHub" on your desktop to start it.
echo On first start it asks for your OpenRouter key.
pause
