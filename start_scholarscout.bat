@echo off
setlocal enabledelayedexpansion
title ScholarScout - Academic Research & Funding Intelligence Agent

echo ===============================================================================
echo                ScholarScout Academic Intelligence Server
echo ===============================================================================
echo.

:: 1. Check for Python installation
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found on your PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

echo [1/4] Checking Python environment...
python --version

:: 2. Setup Virtual Environment if missing
if not exist "venv\Scripts\activate.bat" (
    echo [2/4] Creating virtual environment (.venv)...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [WARNING] Could not create virtual environment. Using system Python instead.
    )
)

if exist "venv\Scripts\activate.bat" (
    echo [2/4] Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo [2/4] Using active Python environment...
)

:: 3. Install requirements
echo [3/4] Verifying dependencies from requirements.txt...
python -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some dependencies failed to install. Retrying in verbose mode...
    python -m pip install -r requirements.txt
)

:: 4. Start Server
echo [4/4] Starting ScholarScout FastAPI Uvicorn Server on port 8003...
echo.
echo ===============================================================================
echo   Dashboard URL: http://127.0.0.1:8003
echo   Swagger Docs:  http://127.0.0.1:8003/docs
echo   Press CTRL+C in this terminal window to stop the server safely.
echo ===============================================================================
echo.

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8003 --reload

pause
