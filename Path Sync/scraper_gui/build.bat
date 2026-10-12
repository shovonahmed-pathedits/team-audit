@echo off
echo ========================================
echo   Path Sync - Build Script
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] Checking environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found! Please install Python 3.10+
    pause
    exit /b 1
)

echo [2/2] Building executable...
echo.
pyinstaller Path-Sync.spec --clean

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build Complete!
echo ========================================
echo.
echo Output: dist\Path-Sync.exe
echo.
pause