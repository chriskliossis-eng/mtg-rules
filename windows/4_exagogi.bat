@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================
echo   fbwatch - Εξαγωγή περιόδου (CSV, JSON, HTML, PDF)
echo ============================================
echo Γράψε ημερομηνίες με τη μορφή ΗΗ/ΜΜ/ΕΕΕΕ, π.χ. 01/09/2026
echo Άφησε κενό και πάτα Enter για "χωρίς όριο".
echo.
set /p APO=Από ημερομηνία: 
set /p EOS=Έως ημερομηνία: 
set ARGS=
if not "%APO%"=="" set ARGS=%ARGS% --from %APO%
if not "%EOS%"=="" set ARGS=%ARGS% --to %EOS%
".venv\Scripts\fbwatch.exe" export --format all %ARGS%
echo.
echo Τα αρχεία είναι στον φάκελο data\exports (ανοίγει τώρα).
start "" "data\exports"
pause
