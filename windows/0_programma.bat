@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo Δεν έχει γίνει εγκατάσταση. Τρέξε πρώτα το 1_egkatastasi.bat
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m fbwatch gui
