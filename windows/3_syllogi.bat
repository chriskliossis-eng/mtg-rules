@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================
echo   fbwatch - Συλλογή νέων posts και screenshots
echo ============================================
echo.
".venv\Scripts\fbwatch.exe" run
echo.
echo Τα screenshots είναι στον φάκελο data\screenshots
echo.
pause
