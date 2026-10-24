@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys, struct; sys.exit(not (sys.version_info[:2] == (3, 11) and struct.calcsize('P') == 8))" >nul 2>&1
    if not errorlevel 1 goto existing
)
py -3.11 -c "import sys, struct; sys.exit(not (sys.version_info[:2] == (3, 11) and struct.calcsize('P') == 8))" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys, struct; sys.exit(not (sys.version_info[:2] == (3, 11) and struct.calcsize('P') == 8))" >nul 2>&1
if not errorlevel 1 goto python
echo Python 3.11 64-bit is required. Install it from python.org, then retry.
echo See README.md and docs/teaching-guide.zh-TW.md for classroom setup.
set "result=1"
goto finish
:existing
".venv\Scripts\python.exe" scripts\bootstrap.py %*
goto capture
:launcher
py -3.11 scripts\bootstrap.py %*
goto capture
:python
python scripts\bootstrap.py %*
:capture
set "result=%errorlevel%"
:finish
if not "%result%"=="0" (
    echo Startup failed. Keep the error above and show it to your teacher.
    pause
)
popd
exit /b %result%
