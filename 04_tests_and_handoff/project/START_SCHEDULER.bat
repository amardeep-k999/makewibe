@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run START.bat first to install the dependencies.
 pause
 exit /b 1
)
.venv\Scripts\python.exe scheduler.py
pause
