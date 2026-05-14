@echo off
cd /d "%~dp0"
title Claude Usage Monitor – Build

echo ============================================================
echo  Claude Usage Monitor – EXE Build
echo ============================================================
echo.

:: ── Step 1: Install project dependencies ─────────────────────────────────────
::    uv sync is fast (< 1s) when everything is already installed.
echo [1/3] Installing dependencies...
uv sync
if errorlevel 1 (
    echo.
    echo ERROR: uv not found or dependency installation failed.
    echo        Is uv installed? https://docs.astral.sh/uv/
    pause & exit /b 1
)

:: ── Step 2: Check PyInstaller ─────────────────────────────────────────────────
::    Installed once into the venv; subsequent calls take < 1s.
uv run pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [2/3] Installing PyInstaller (one-time)...
    uv pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo ERROR: PyInstaller installation failed.
        pause & exit /b 1
    )
) else (
    echo [2/3] PyInstaller found.
)

:: ── Step 3: Build ─────────────────────────────────────────────────────────────
::    Uses ClaudeUsageMonitor.spec (all build parameters stored there).
::    The build\ folder is kept as cache → rebuilds take ~10s instead of ~30s.
::    Only the old EXE is deleted beforehand.
if exist dist\ClaudeUsageMonitor.exe del /q dist\ClaudeUsageMonitor.exe

echo [3/3] Building EXE...
echo        (First build ~30s  |  Rebuild with cache ~10s)
echo.
uv run pyinstaller ClaudeUsageMonitor.spec

if errorlevel 1 (
    echo.
    echo ERROR: Build failed.
    echo        Check the error message above.
    echo        For strange errors: delete the build\ folder and try again.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  Done:  dist\ClaudeUsageMonitor.exe
echo ============================================================
pause
