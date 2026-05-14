@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Claude Usage Monitor - Clean Build

echo ============================================================
echo   Claude Usage Monitor - Clean Build
echo   ^(deletes build cache for a fresh rebuild^)
echo ============================================================
echo.

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
echo   Cache cleared. Starting build...
echo.

call build_exe.bat
