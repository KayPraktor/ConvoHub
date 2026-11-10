# Builds packaging\Output\ConvoHub-Setup.exe
#   1) PyInstaller  -> dist\ConvoHub  (ConvoHub.exe + convohub-mcp.exe)
#   2) Inno Setup   -> packaging\Output\ConvoHub-Setup.exe
# Needs: uv, and Inno Setup 6 (winget install JRSoftware.InnoSetup)
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Select-String -Path "$root\pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "ConvoHub $version"

Write-Host "1/2 PyInstaller..."
uv run --group build pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\convohub.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$iscc = @(
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }

Write-Host "2/2 Inno Setup..."
& $iscc "/DAppVersion=$version" "packaging\convohub.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

$out = Get-Item "packaging\Output\ConvoHub-Setup.exe"
Write-Host ("Done: {0} ({1:N1} MB)" -f $out.FullName, ($out.Length / 1MB))
