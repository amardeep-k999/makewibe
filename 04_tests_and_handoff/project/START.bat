@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
 echo Install Python 3.11 or newer and enable Add Python to PATH, then try again.
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
 python -m venv .venv
 if errorlevel 1 goto failed
)
if not exist ".venv\installed.txt" (
 .venv\Scripts\python.exe -m pip install -r requirements.txt
 if errorlevel 1 goto failed
 echo installed>.venv\installed.txt
)
.venv\Scripts\python.exe -m flask --app app seed
if errorlevel 1 goto failed
echo.
echo Open http://127.0.0.1:5055 in your browser.
echo Keep this window open. Press Ctrl+C to stop the server.
.venv\Scripts\python.exe app.py
pause
exit /b
:failed
echo Setup failed. Read the message above, check Python and your internet connection, and try again.
pause
exit /b 1
