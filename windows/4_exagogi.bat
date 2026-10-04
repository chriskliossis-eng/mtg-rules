@echo off
cd /d "%~dp0.."
echo fbwatch - Exagogi periodou (CSV, JSON, HTML, PDF)
echo Grapse imerominies me ti morfi HH/MM/EEEE, p.x. 01/09/2026. Keno = xoris orio.
echo.
set /p APO=Apo imerominia: 
set /p EOS=Eos imerominia: 
set ARGS=
if not "%APO%"=="" set ARGS=%ARGS% --from %APO%
if not "%EOS%"=="" set ARGS=%ARGS% --to %EOS%
".venv\Scripts\fbwatch.exe" export --format all %ARGS%
echo.
start "" "data\exports"
pause
