@echo off
cd /d "%~dp0"
:: Runs the app directly from the venv – no EXE build needed.
:: Useful for quick testing during development.
.venv\Scripts\pythonw.exe -m claude_usage_monitor
