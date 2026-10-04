@echo off
cd /d "%~dp0.."
".venv\Scripts\fbwatch.exe" status
echo.
".venv\Scripts\fbwatch.exe" list
pause
