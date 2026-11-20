@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE="
set "PY_ARG="
call :find_python

if not defined PY_EXE (
  echo Python 3.10+ not found. Attempting automatic install via winget...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo Please install Python 3.10+ from https://www.python.org/downloads/ and double-click this script again.
    pause
    exit /b 1
  )
  call :find_python
)

if not defined PY_EXE (
  echo Python 3.10+ installed but not found yet. Close this window and double-click Install-Windows.bat again.
  pause
  exit /b 1
)

"%PY_EXE%" %PY_ARG% "%~dp0install.py"
if errorlevel 1 (
  echo Installation failed. Check Python version ^(3.10+ required^).
  pause
  exit /b 1
)
exit /b 0

:find_python
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "PY_EXE=py"
  set "PY_ARG=-3"
  exit /b 0
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "PY_EXE=python"
  set "PY_ARG="
  exit /b 0
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    set "PY_ARG="
    exit /b 0
  )
)
exit /b 0
