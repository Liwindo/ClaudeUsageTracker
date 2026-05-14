@echo off
cd /d "%~dp0"
title Claude Usage Monitor – Clean Build

echo Deleting build cache (build\ and dist\) for a clean rebuild...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo Done.
echo.

:: Start the normal build process
call build_exe.bat
