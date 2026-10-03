@echo off
title ScholarScout - Automated Test Runner
echo ===============================================================================
echo                ScholarScout Automated Test Suite Runner
echo ===============================================================================
echo.

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

echo Running all 143 automated regression tests across all 12 modules...
echo.

python -m pytest -v --tb=short

echo.
echo ===============================================================================
echo Test run complete.
echo ===============================================================================
pause
