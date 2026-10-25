@echo off
cd /d "%~dp0"
echo Demo ma'lumot yangilanmoqda...
python seed_demo.py --reset
echo.
echo Sayt ishga tushdi: http://127.0.0.1:5000  (to'xtatish: Ctrl+C)
python app.py
pause
