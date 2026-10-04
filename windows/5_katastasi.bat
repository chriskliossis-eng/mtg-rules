@echo off
chcp 65001 >nul
cd /d "%~dp0.."
".venv\Scripts\fbwatch.exe" status
echo.
".venv\Scripts\fbwatch.exe" list
echo.
pause
