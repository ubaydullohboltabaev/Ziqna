@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Windows ko'pincha faylni "bot_token.txt.txt" deb saqlaydi (kengaytma yashirin) - to'g'rilab qo'yamiz
if not exist bot_token.txt if exist bot_token.txt.txt ren bot_token.txt.txt bot_token.txt
if exist bot_token.txt goto run
echo bot_token.txt fayli topilmadi.
echo 1. Telegram'da @BotFather ga yozing va /newbot bilan bot yarating.
echo 2. U bergan tokenni shu papkadagi bot_token.txt fayliga yozing - faqat tokenning o'zi.
pause
exit /b
:run
rem Haqiqiy narxlar bazasi - real.bat yaratgan
set NARXTOP_DB=%~dp0narxtop_real.db
python bot.py
echo.
echo Bot to'xtadi. Yuqoridagi xabarni o'qing yoki skrinshot yuboring.
pause
