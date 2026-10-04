@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================
echo   fbwatch - Έλεγχος πρόσβασης (χωρίς αποθήκευση)
echo ============================================
echo Θα ανοίξει ένα παράθυρο browser για κάθε σελίδα. Μην το αγγίξεις, κλείνει μόνο του.
echo.
".venv\Scripts\fbwatch.exe" check --headed --dump
echo.
echo Αν στη "Σύνοψη" βλέπεις "ok" με αριθμό posts, όλα καλά: τρέξε το 3_syllogi.bat
echo Αν βλέπεις "empty", "login_wall" ή "unavailable", στείλε τα αρχεία από τον φάκελο data\debug
echo.
pause
