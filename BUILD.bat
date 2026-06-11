@echo off
title Build EXE - Teacher Substitution System
color 0A

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   GNS Substitution System — EXE Builder      ║
echo  ║   Gyan Niketan School                        ║
echo  ╚══════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM ── Step 1: Check Python ──────────────────────────
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python is not installed or not in PATH.
    echo  Download from: https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)
python --version
echo       OK
echo.

REM ── Step 2: Install/upgrade pip ──────────────────
echo [2/5] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo       OK
echo.

REM ── Step 3: Install all dependencies + PyInstaller ──
echo [3/5] Installing dependencies + PyInstaller...
pip install fastapi "uvicorn[standard]" ortools httpx pydantic pywebview python-dotenv pyinstaller ^
    --trusted-host pypi.org --trusted-host files.pythonhosted.org --quiet
if errorlevel 1 (
    echo  ERROR: Failed to install packages. Check your internet connection.
    pause
    exit /b 1
)
echo       Done.
echo.

REM ── Step 4: Verify .env file ─────────────────────
echo [4/5] Checking .env credentials file...
if not exist ".env" (
    echo.
    echo  WARNING: .env file not found!
    echo  Creating a template .env — you MUST fill in your Supabase credentials.
    echo.
    echo SUPABASE_PROJECT_URL=https://YOUR_PROJECT_ID.supabase.co > .env
    echo SUPABASE_SERVICE_KEY=your_service_role_key_here >> .env
    echo  Template created. Edit .env with your real credentials before running the EXE.
    echo.
) else (
    echo       .env found OK
)
echo.

REM ── Step 5: Build the EXE ────────────────────────
echo [5/5] Building EXE with PyInstaller (this may take 2-5 minutes)...
echo       Please wait...
echo.

pyinstaller GNS.spec --noconfirm --clean

if errorlevel 1 (
    echo.
    echo  ╔══════════════════════════════════════════════╗
    echo  ║   BUILD FAILED — See errors above            ║
    echo  ╚══════════════════════════════════════════════╝
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   BUILD SUCCESSFUL!                          ║
echo  ║                                              ║
echo  ║   Your EXE is in:                            ║
echo  ║   dist\GNS-SubstitutionSystem\               ║
echo  ║                                              ║
echo  ║   To run: double-click                       ║
echo  ║   GNS-SubstitutionSystem.exe inside dist\    ║
echo  ║                                              ║
echo  ║   IMPORTANT: Copy your .env file into the    ║
echo  ║   dist\GNS-SubstitutionSystem\ folder too!   ║
echo  ╚══════════════════════════════════════════════╝
echo.

REM ── Copy .env into dist folder automatically ─────
if exist "dist\GNS-SubstitutionSystem\" (
    copy /Y ".env" "dist\GNS-SubstitutionSystem\.env" >nul
    echo  .env copied to dist folder automatically.
    echo.
)

pause
