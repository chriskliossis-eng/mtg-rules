@echo off
cd /d "%~dp0.."
echo ============================================
echo   fbwatch - Egkatastasi (mia fora)
echo ============================================
echo.
set PY=
py -3 --version >nul 2>nul && set PY=py -3
if "%PY%"=="" python --version >nul 2>nul && set PY=python
if "%PY%"=="" goto nopython
echo [1/4] Dimiourgia perivallontos Python...
if not exist ".venv" %PY% -m venv .venv
if errorlevel 1 goto fail
echo [2/4] Egkatastasi tou fbwatch...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -e . tzdata
if errorlevel 1 goto fail
echo [3/4] Katevasma tou browser (Chromium, ~150MB)...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto fail
echo [4/4] Rythmiseis...
if not exist "config.yaml" copy /y config.example.yaml config.yaml >nul
echo.
echo H egkatastasi oloklirothike. Anoigei to programma.
echo Apo edo kai pera, gia na to anoigeis: diplo klik sto 0_programma.bat
echo.
pause
start "" ".venv\Scripts\pythonw.exe" -m fbwatch gui
exit /b 0
:nopython
echo DEN vrethike i Python.
echo Katevase tin apo https://www.python.org/downloads/
echo kai stin egkatastasi tsekare to "Add python.exe to PATH".
echo Meta xanatrexe auto to arxeio.
pause
exit /b 1
:fail
echo Sfalma stin egkatastasi. Elegxe ti syndesi sto internet kai xanaprospathise.
pause
exit /b 1
