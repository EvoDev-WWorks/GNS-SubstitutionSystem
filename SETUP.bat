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
venv\Scripts\pip install fastapi "uvicorn[standard]" ortools httpx ^
    --trusted-host pypi.org --trusted-host files.pythonhosted.org
echo       Done.
echo.

echo [3/3] Verifying connection to Supabase...
venv\Scripts\python.exe -c "import httpx; r=httpx.get('https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1/teachers?limit=1',headers={'apikey':'REMOVED'},verify=False); print('  Supabase connection OK' if r.status_code==200 else f'  Warning: status {r.status_code}')"

echo.
echo  =====================================================
echo   SETUP COMPLETE
echo   Now double-click START.bat to run the system
echo  =====================================================
echo.
pause
