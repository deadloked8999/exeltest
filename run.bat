@echo off
echo ====================================
echo   Excel Telegram Bot - Starting
echo ====================================
echo.

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Starting bot...
python bot.py

pause


