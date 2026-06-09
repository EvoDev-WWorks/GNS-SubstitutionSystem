@echo off
title Setup - Teacher Substitution System
echo.
echo  =====================================================
echo   SETUP - Teacher Substitution System
echo   Run this ONCE before first use
echo  =====================================================
echo.

cd /d "%~dp0"

echo [1/3] Creating Python virtual environment...
python -m venv venv
echo       Done.
echo.

echo [2/3] Installing required packages...
venv\Scripts\pip install fastapi "uvicorn[standard]" ortools httpx python-dotenv ^
    --trusted-host pypi.org --trusted-host files.pythonhosted.org
echo       Done.
echo.

echo [3/3] Checking .env file...
if exist ".env" (echo   .env found OK) else (echo   WARNING: .env file missing! Create it before starting.)

echo.
echo  =====================================================
echo   SETUP COMPLETE
echo   Now double-click START.bat to run the system
echo  =====================================================
echo.
pause
