#!/bin/bash

echo "===================================="
echo "  Excel Telegram Bot - Setup"
echo "===================================="
echo ""

echo "[1/5] Checking Python installation..."
python3 --version
if [ $? -ne 0 ]; then
    echo "Error: Python 3 is not installed!"
    exit 1
fi
echo ""

echo "[2/5] Creating virtual environment..."
python3 -m venv venv
echo ""

echo "[3/5] Activating virtual environment..."
source venv/bin/activate
echo ""

echo "[4/5] Installing dependencies..."
pip install -r requirements.txt
echo ""

echo "[5/5] Creating .env file..."
if [ ! -f .env ]; then
    cp env.example .env
    echo ".env file created! Please edit it with your credentials."
else
    echo ".env file already exists. Skipping."
fi
echo ""

echo "===================================="
echo "  Setup completed successfully!"
echo "===================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials"
echo "2. Create PostgreSQL database: excel_bot"
echo "3. Run: ./run.sh or python bot.py"
echo ""


