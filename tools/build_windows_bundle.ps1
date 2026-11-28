# Builds cvprism-windows.zip: official embeddable Python + cvprism + all libraries. No install needed.
# Runs on GitHub Actions (windows-latest) with setup-python of the SAME minor version as $PyVersion,
# so binary wheels match the embedded interpreter.
param(
    [string]$PyVersion = "3.12.10",
    [string]$Out = "dist\cvprism-windows"
)
$ErrorActionPreference = "Stop"

$root = Resolve-Path "$PSScriptRoot\.."
$out = Join-Path $root $Out
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force "$out\python", "$out\lib" | Out-Null

# 1. Official embeddable Python from python.org
$zip = Join-Path $env:RUNNER_TEMP "python-embed.zip"
$url = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
Write-Host "Downloading $url"
Invoke-WebRequest -Uri $url -OutFile $zip
Expand-Archive -Path $zip -DestinationPath "$out\python" -Force

# 2. Let the embedded interpreter see ..\lib and enable site-packages
$pth = Get-ChildItem "$out\python" -Filter "python3*._pth" | Select-Object -First 1
$lines = Get-Content $pth.FullName | ForEach-Object { if ($_ -eq "#import site") { "import site" } else { $_ } }
$lines += "..\lib"
Set-Content -Path $pth.FullName -Value $lines -Encoding ascii

# 3. cvprism and every dependency (PDF + Word extras) into lib
python -m pip install --upgrade pip | Out-Null
python -m pip install --no-warn-script-location --target "$out\lib" "$root[all]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# 4. Launchers
@'
@echo off
rem Double-click me. First time: setup opens in your browser. After that: the cvprism app.
setlocal
set "HERE=%~dp0"
"%HERE%python\python.exe" -m cvprism status >nul 2>&1
if errorlevel 1 (
  "%HERE%python\python.exe" -m cvprism init --web
  if errorlevel 1 exit /b 1
)
echo.
echo Opening cvprism in your browser. Keep this window open while you use it.
"%HERE%python\python.exe" -m cvprism app
endlocal
'@ | Set-Content -Path "$out\Open cvprism.bat" -Encoding ascii

@'
@"%~dp0python\python.exe" -m cvprism %*
'@ | Set-Content -Path "$out\cvprism.bat" -Encoding ascii

@'
cvprism for Windows (no Python install needed)
================================================

1. Keep this folder somewhere permanent, e.g. Documents\cvprism.
   (Automatic capture and the background agent point here.)
2. Double-click "Open cvprism.bat".
   The first time, a setup page opens in your browser. After that, the cvprism app opens.

Power users: cvprism.bat runs the command line, e.g.  cvprism.bat demo --out %USERPROFILE%\cvprism-demo
Documentation: https://sayantanonfire.github.io/cvprism/
Licence: Apache-2.0 (see LICENSE). Bundled Python: PSF licence (python\LICENSE.txt).
'@ | Set-Content -Path "$out\READ ME FIRST.txt" -Encoding utf8

Copy-Item "$root\LICENSE" "$out\LICENSE"

# 5. Zip
$zipOut = Join-Path $root "dist\cvprism-windows.zip"
if (Test-Path $zipOut) { Remove-Item $zipOut }
Compress-Archive -Path "$out\*" -DestinationPath $zipOut
Write-Host "Built $zipOut ($([math]::Round((Get-Item $zipOut).Length / 1MB, 1)) MB)"
