@echo off
REM One-command launcher for TR Insight (Windows).
cd /d "%~dp0"
python -m pip install --quiet flask pytr yfinance
echo Starting TR Insight on http://127.0.0.1:8000
python app.py
