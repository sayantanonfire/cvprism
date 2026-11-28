# Smoke-tests an unzipped bundle exactly as a user would run it (no system Python on PATH involved).
param([string]$Bundle = "dist\cvprism-windows")
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
$b = Join-Path $root $Bundle
$env:CVPRISM_HOME = Join-Path $env:RUNNER_TEMP "bundle-home"
$py = Join-Path $b "python\python.exe"

& $py -m cvprism --version
if ($LASTEXITCODE -ne 0) { throw "version failed" }
& cmd /c "`"$b\cvprism.bat`" init --name bundle --role hub --vault `"$env:RUNNER_TEMP\bundle-vault`" --yes"
if ($LASTEXITCODE -ne 0) { throw "init failed" }
& cmd /c "`"$b\cvprism.bat`" log --raw `"Built a Windows bundle smoke test`" --skill powershell --depth 2"
if ($LASTEXITCODE -ne 0) { throw "log failed" }
$demo = Join-Path $env:RUNNER_TEMP "bundle-demo"
& cmd /c "`"$b\cvprism.bat`" demo --out `"$demo`" --format pdf,docx,md"
if ($LASTEXITCODE -ne 0) { throw "demo failed" }
$pdfs = Get-ChildItem -Recurse $demo -Filter cv.pdf
if ($pdfs.Count -lt 4) { throw "expected 4 PDFs, found $($pdfs.Count)" }
& cmd /c "`"$b\cvprism.bat`" doctor"
Write-Host "Bundle smoke test passed: $($pdfs.Count) PDFs built with the embedded Python."
