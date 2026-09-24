@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m src.desktop
if errorlevel 1 pause
