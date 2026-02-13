@echo off
chcp 65001 >nul
:: Set current directory
cd /d "%~dp0"

echo ==========================================
echo       Prompt Optimizer Bot Launcher
echo ==========================================

:: Check if .venv exists
if exist .venv goto :found
echo [ERROR] Virtual environment (.venv) not found!
echo Please ensure you have installed the project dependencies.
echo You can create it using: python -m venv .venv
pause
exit /b

:found
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate

echo [INFO] Starting application...
echo [INFO] Press Ctrl+C to stop the server.
echo.
python -m app.main

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
