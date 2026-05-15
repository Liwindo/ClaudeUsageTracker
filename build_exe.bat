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

:: ── Step 1: Install all dependencies (including PyInstaller) ─────────────────
echo [1/2] Installing dependencies...
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

:: ── Step 2: Build EXE ─────────────────────────────────────────────────────────
if exist dist\ClaudeUsageTracker.exe (
    echo   Removing old EXE...
    del /q dist\ClaudeUsageTracker.exe
)

echo [2/2] Building EXE...
echo   ^(First build ~30s  ^|  Rebuild with cache ~10s^)
echo.
.venv\Scripts\pyinstaller.exe ClaudeUsageTracker.spec
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
