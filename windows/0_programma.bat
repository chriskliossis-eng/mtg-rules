@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" goto noinstall
start "" ".venv\Scripts\pythonw.exe" -m fbwatch gui
exit /b 0
:noinstall
echo Den exei ginei egkatastasi. Trexe prota to 1_egkatastasi.bat
pause
exit /b 1
