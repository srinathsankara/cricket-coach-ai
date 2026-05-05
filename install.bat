@echo off
title Cricket Coach AI — Setup
echo.
echo  ============================================
echo   Cricket Coach AI — First Time Setup
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed!
    echo.
    echo  Please download Python 3.9+ from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During installation, tick the box
    echo  that says "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo  Python found. Installing libraries...
echo  (This may take a few minutes on first run)
echo.

pip install flask mediapipe opencv-python numpy reportlab

echo.
echo  ============================================
echo   Setup complete!
echo   Double-click start.bat to launch the app.
echo  ============================================
echo.
pause
