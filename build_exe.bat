@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Claude Usage Monitor - Build

echo ============================================================
echo   Claude Usage Monitor - EXE Build
echo ============================================================
echo.
echo   Directory : %CD%
for /f "tokens=*" %%v in ('uv --version 2^>nul') do echo   uv        : %%v
echo.

:: ── Step 1: Install project dependencies ─────────────────────────────────────
echo [1/3] Installing project dependencies...
uv sync
if errorlevel 1 (
    echo.
    echo   ERROR: "uv sync" failed.
    echo.
    echo   Possible causes:
    echo     - uv is not installed. Get it from: https://docs.astral.sh/uv/
    echo     - pyproject.toml is missing or corrupted
    echo.
    pause & exit /b 1
)
echo   Dependencies OK.
echo.

:: ── Step 2: Ensure PyInstaller is available ───────────────────────────────────
uv run pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [2/3] Installing PyInstaller ^(one-time^)...
    uv pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo   ERROR: PyInstaller installation failed.
        echo   Try manually: uv pip install pyinstaller
        echo.
        pause & exit /b 1
    )
    echo   PyInstaller installed successfully.
) else (
    for /f "tokens=*" %%v in ('uv run pyinstaller --version 2^>nul') do echo [2/3] PyInstaller %%v - OK.
)
echo.

:: ── Step 3: Build EXE ─────────────────────────────────────────────────────────
if exist dist\ClaudeUsageMonitor.exe (
    echo   Removing old EXE...
    del /q dist\ClaudeUsageMonitor.exe
)

echo [3/3] Building EXE...
echo   ^(First build ~30s  ^|  Rebuild with cache ~10s^)
echo.
uv run pyinstaller ClaudeUsageMonitor.spec
set BUILD_ERR=%errorlevel%

echo.
if %BUILD_ERR% neq 0 (
    echo   ERROR: PyInstaller failed ^(exit code %BUILD_ERR%^).
    echo.
    if exist "build\ClaudeUsageMonitor\warn-ClaudeUsageMonitor.txt" (
        echo   --- PyInstaller warnings ^(last 20 lines^) ---
        powershell -NoProfile -Command "Get-Content 'build\ClaudeUsageMonitor\warn-ClaudeUsageMonitor.txt' | Select-Object -Last 20"
        echo   ---
        echo.
    )
    echo   Tips:
    echo     - Run build_exe_clean.bat to delete the cache and try again
    echo     - Check the full output above for the first ERROR line
    echo.
    pause & exit /b %BUILD_ERR%
)

if not exist dist\ClaudeUsageMonitor.exe (
    echo   ERROR: PyInstaller reported success but the EXE was not created.
    echo   Check the output above for clues.
    echo.
    pause & exit /b 1
)

for %%F in (dist\ClaudeUsageMonitor.exe) do set EXE_SIZE=%%~zF
set /a EXE_MB=%EXE_SIZE% / 1048576

echo ============================================================
echo   Done:  dist\ClaudeUsageMonitor.exe  ^(%EXE_MB% MB^)
echo ============================================================
pause
