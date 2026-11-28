@echo off
rem cvprism bootstrap for Windows. Works from a git clone or a USB drive.
rem Creates a venv in %LOCALAPPDATA%\cvprism (never on the USB drive), installs cvprism
rem from this folder, then runs first-time setup (any arguments go to `cvprism init`).
setlocal EnableExtensions

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "PY="
for %%C in ("py -3" python python3) do (
  if not defined PY (
    %%~C -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=%%~C"
  )
)
if not defined PY (
  echo cvprism needs Python 3.10 or newer.
  echo Install it with:  winget install Python.Python.3.12
  echo or download it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  exit /b 1
)

if defined CVPRISM_HOME (set "DATA=%CVPRISM_HOME%") else (set "DATA=%LOCALAPPDATA%\cvprism")
set "VENV=%DATA%\venv"

if not exist "%VENV%\Scripts\python.exe" (
  echo Creating environment in %VENV%
  if not exist "%DATA%" mkdir "%DATA%"
  %PY% -m venv "%VENV%" || exit /b 1
)

echo Installing cvprism from %HERE%
if exist "%HERE%\wheelhouse" (
  "%VENV%\Scripts\python.exe" -m pip install -q --no-index --find-links "%HERE%\wheelhouse" "%HERE%" || exit /b 1
) else (
  "%VENV%\Scripts\python.exe" -m pip install -q --upgrade pip >nul 2>&1
  "%VENV%\Scripts\python.exe" -m pip install -q "%HERE%[all]"
  if errorlevel 1 "%VENV%\Scripts\python.exe" -m pip install -q "%HERE%" || exit /b 1
)

set "CVPRISM=%VENV%\Scripts\cvprism.exe"

rem No arguments (double-click): set up in the browser, then open the app.
if "%~1"=="" (
  "%CVPRISM%" status >nul 2>&1
  if errorlevel 1 (
    "%CVPRISM%" init --web
    if errorlevel 1 exit /b 1
  )
  echo.
  echo Opening cvprism in your browser. Keep this window open while you use it.
  "%CVPRISM%" app
  endlocal
  exit /b 0
)

"%CVPRISM%" status >nul 2>&1
if errorlevel 1 (
  "%CVPRISM%" init %*
  if errorlevel 1 exit /b 1
) else (
  "%CVPRISM%" status
)

echo.
echo cvprism is installed at: %CVPRISM%
echo To use `cvprism` from any terminal, add this folder to your PATH: %VENV%\Scripts
echo Next time, just double-click start.bat to open the cvprism app.
endlocal
