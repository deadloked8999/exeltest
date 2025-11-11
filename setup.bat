@echo off
echo ====================================
echo   Excel Telegram Bot - Setup
echo ====================================
echo.

echo [1/5] Checking Python installation...
python --version
if errorlevel 1 (
    echo Error: Python is not installed!
    pause
    exit /b 1
)
echo.

echo [2/5] Creating virtual environment...
python -m venv venv
echo.

echo [3/5] Activating virtual environment...
call venv\Scripts\activate.bat
echo.

echo [4/5] Installing dependencies...
pip install -r requirements.txt
echo.

echo [5/5] Creating .env file...
if not exist .env (
    copy env.example .env
    echo .env file created! Please edit it with your credentials.
) else (
    echo .env file already exists. Skipping.
)
echo.

echo ====================================
echo   Setup completed successfully!
echo ====================================
echo.
echo Next steps:
echo 1. Edit .env file with your credentials
echo 2. Create PostgreSQL database: excel_bot
echo 3. Run: python bot.py
echo.
pause


