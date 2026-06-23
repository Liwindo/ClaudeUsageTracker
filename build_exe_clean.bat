@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Claude Usage Tracker - Clean Build

echo ============================================================
echo   Claude Usage Tracker - Clean Build
echo   ^(deletes build cache, then runs the full gated build^)
echo ============================================================
echo.

REM Pre-flight: if the EXE is locked we cannot rebuild it, so bail out BEFORE
REM nuking the cache - otherwise a locked file costs a slow full rebuild for
REM nothing. The gated build (CHANGELOG, compile, tests) lives in build_exe.bat;
REM this script only adds the cache wipe on top.
if exist dist\ClaudeUsageTracker.exe (
    del /q dist\ClaudeUsageTracker.exe 2>nul
    if exist dist\ClaudeUsageTracker.exe (
        echo   ERROR: dist\ClaudeUsageTracker.exe is locked - the app is probably
        echo   still running ^(tray icon -^> Quit^), or an antivirus / cloud-sync is
        echo   holding it. Close it and re-run. The build cache is left intact.
        echo.
        pause & exit /b 1
    )
)

if exist build (
    echo   Deleting build\ ...
    rmdir /s /q build
    echo   Done.
) else (
    echo   build\ does not exist - nothing to delete.
)

if exist dist (
    echo   Deleting dist\ ...
    rmdir /s /q dist
    echo   Done.
) else (
    echo   dist\ does not exist - nothing to delete.
)

echo.
echo   Cache cleared. Starting full gated build...
echo.

call build_exe.bat
