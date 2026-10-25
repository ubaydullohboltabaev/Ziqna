@echo off
cd /d "%~dp0"
if not exist bot_token.txt (
  echo bot_token.txt fayli topilmadi.
  echo 1. Telegram'da @BotFather ga yozing, /newbot buyrug'i bilan bot yarating.
  echo 2. U bergan tokenni shu papkadagi bot_token.txt fayliga yozing (faqat token, boshqa narsa emas).
  pause
  exit /b
)
rem Haqiqiy narxlar bazasi (real.bat yaratgan)
set NARXTOP_DB=%~dp0narxtop_real.db
python bot.py
pause
