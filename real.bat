@echo off
cd /d "%~dp0"
rem Haqiqiy narxlar alohida bazada saqlanadi (demo baza o'zgarmaydi).
set NARXTOP_DB=%~dp0narxtop_real.db
echo Texnomart narxlari yig'ilmoqda (taxminan 1 daqiqa)...
python run_scrape.py
echo.
echo Sayt ishga tushdi: http://127.0.0.1:5000  (to'xtatish: Ctrl+C)
python app.py
pause
