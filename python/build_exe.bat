@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Claude Usage Tracker - Build

echo ============================================================
echo   Claude Usage Tracker - EXE Build
echo ============================================================
echo.
echo   Directory : %CD%
for /f "tokens=*" %%v in ('uv --version 2^>nul') do echo   uv        : %%v
echo.

REM --- Step 1: CHANGELOG guard (same rule the GitHub release enforces) ---
echo [1/5] Checking CHANGELOG.md for the current version's notes...
powershell -NoProfile -ExecutionPolicy Bypass -File ..\scripts\check_changelog.ps1
if errorlevel 1 (
    echo.
    echo   ERROR: CHANGELOG guard failed ^(see message above^).
    echo   The GitHub release enforces the same rule - add the section first.
    echo.
    pause & exit /b 1
)
echo.

REM --- Step 2: Install all dependencies (including PyInstaller) ---
echo [2/5] Installing dependencies...
uv sync --extra dev
if errorlevel 1 (
    echo.
    echo   ERROR: "uv sync --extra dev" failed.
    echo.
    echo   Possible causes:
    echo     - uv is not installed. Get it from: https://docs.astral.sh/uv/
    echo     - pyproject.toml is missing or corrupted
    echo.
    pause & exit /b 1
)

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo.
    echo   ERROR: pyinstaller.exe not found in .venv\Scripts\ after sync.
    echo   This is unexpected. Try: uv sync --extra dev --reinstall
    echo.
    pause & exit /b 1
)

for /f "tokens=*" %%v in ('.venv\Scripts\pyinstaller.exe --version 2^>nul') do echo   PyInstaller %%v - OK.
echo.

REM --- Step 3: Byte-compile sources (fast structural check, as CI does) ---
echo [3/5] Byte-compiling sources...
uv run python -m compileall -q src\claude_usage_monitor
if errorlevel 1 (
    echo.
    echo   ERROR: Byte-compilation failed - there is a syntax error in the sources.
    echo.
    pause & exit /b 1
)
echo.

REM --- Step 4: Run the test suite (gate the build, as CI / release do) ---
echo [4/5] Running tests...
uv run pytest -q
if errorlevel 1 (
    echo.
    echo   ERROR: Tests failed - aborting before building the EXE.
    echo   The GitHub release runs the same suite and would not publish.
    echo.
    pause & exit /b 1
)
echo.

REM --- Step 5: Build EXE ---
REM Delete the old EXE first and confirm it is gone. If it cannot be removed
REM the file is locked (the app is still running, or an AV / cloud-sync holds
REM it) - fail loudly instead of letting PyInstaller silently leave a stale EXE.
if exist dist\ClaudeUsageTracker.exe (
    echo   Removing old EXE...
    del /q dist\ClaudeUsageTracker.exe 2>nul
    if exist dist\ClaudeUsageTracker.exe (
        echo.
        echo   ERROR: Could not delete dist\ClaudeUsageTracker.exe - it is locked.
        echo   The app is probably still running ^(tray icon -^> Quit^), or an
        echo   antivirus / cloud-sync is holding the file. Close it and re-run.
        echo   Aborting so the build cannot leave a stale EXE behind.
        echo.
        pause & exit /b 1
    )
)

echo [5/5] Building EXE...
echo   ^(First build ~30s  ^|  Rebuild with cache ~10s^)
echo.
.venv\Scripts\pyinstaller.exe ClaudeUsageTracker.spec --noconfirm
set BUILD_ERR=%errorlevel%

echo.
if %BUILD_ERR% neq 0 (
    echo   ERROR: PyInstaller failed ^(exit code %BUILD_ERR%^).
    echo.
    if exist "build\ClaudeUsageTracker\warn-ClaudeUsageTracker.txt" (
        echo   --- PyInstaller warnings ^(last 20 lines^) ---
        powershell -NoProfile -Command "Get-Content 'build\ClaudeUsageTracker\warn-ClaudeUsageTracker.txt' | Select-Object -Last 20"
        echo   ---
        echo.
    )
    echo   Tips:
    echo     - Run build_exe_clean.bat to delete the cache and try again
    echo     - Check the full output above for the first ERROR line
    echo.
    pause & exit /b %BUILD_ERR%
)

if not exist dist\ClaudeUsageTracker.exe (
    echo   ERROR: PyInstaller reported success but the EXE was not created.
    echo   Check the output above for clues.
    echo.
    pause & exit /b 1
)

for %%F in (dist\ClaudeUsageTracker.exe) do set EXE_SIZE=%%~zF
set /a EXE_MB=%EXE_SIZE% / 1048576

echo ============================================================
echo   Done:  dist\ClaudeUsageTracker.exe  ^(%EXE_MB% MB^)
echo ============================================================
pause
