@echo off
cd /d "%~dp0.."
echo fbwatch - Elegxos prosvasis (xoris apothikeusi). Tha anoixei browser, min ton aggixeis.
echo.
".venv\Scripts\fbwatch.exe" check --headed --dump
echo.
echo An sti "Synopsi" vlepeis "ok" me arithmo posts, ola kala.
echo An vlepeis "empty", "login_wall" i "unavailable", steile ta arxeia apo ton fakelo data\debug
echo.
pause
