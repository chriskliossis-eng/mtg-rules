@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================
echo   fbwatch - Συνεχής συλλογή κάθε 2 ώρες
echo   Άφησε αυτό το παράθυρο ανοιχτό. Για διακοπή: κλείσε το παράθυρο.
echo ============================================
echo.
".venv\Scripts\fbwatch.exe" run --loop --every 2h
pause
