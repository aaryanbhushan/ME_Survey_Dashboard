@echo off
REM Double-click launcher. Runs from this folder regardless of where it is on
REM disk, so the project can be cloned or unzipped anywhere.
cd /d "%~dp0"

if not exist ".env" (
    echo.
    echo   ERROR: .env not found.
    echo.
    echo   Copy .env.example to .env and fill in the credentials first:
    echo       copy .env.example .env
    echo.
    pause
    exit /b 1
)

python run.py
pause
