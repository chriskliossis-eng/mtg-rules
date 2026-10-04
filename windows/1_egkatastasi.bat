@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================
echo   fbwatch - Εγκατάσταση (μία φορά)
echo ============================================
echo.
set PY=
py -3 --version >nul 2>nul && set PY=py -3
if "%PY%"=="" ( python --version >nul 2>nul && set PY=python )
if "%PY%"=="" (
  echo ΔΕΝ βρέθηκε η Python.
  echo Κατέβασέ την από https://www.python.org/downloads/
  echo και στην εγκατάσταση τσέκαρε το "Add python.exe to PATH".
  echo Μετά ξανατρέξε αυτό το αρχείο.
  pause
  exit /b 1
)
echo [1/4] Δημιουργία περιβάλλοντος Python...
if not exist ".venv" %PY% -m venv .venv
if errorlevel 1 ( echo Σφάλμα στη δημιουργία περιβάλλοντος. & pause & exit /b 1 )
echo [2/4] Εγκατάσταση του fbwatch...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -e . tzdata
if errorlevel 1 ( echo Σφάλμα στην εγκατάσταση. Ελέγξε τη σύνδεση στο internet. & pause & exit /b 1 )
echo [3/4] Κατέβασμα του browser (Chromium, ~150MB)...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 ( echo Σφάλμα στο κατέβασμα του browser. & pause & exit /b 1 )
echo [4/4] Ρυθμίσεις...
if not exist "config.yaml" copy /y config.example.yaml config.yaml >nul
echo.
echo Η εγκατάσταση ολοκληρώθηκε. Ανοίγει το πρόγραμμα.
echo Από εδώ και πέρα, για να το ανοίγεις: διπλό κλικ στο 0_programma.bat
echo.
pause
start "" ".venv\Scripts\pythonw.exe" -m fbwatch gui
