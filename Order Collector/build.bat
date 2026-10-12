@echo off
echo ========================================
echo Building Order Collector (Single EXE)
echo ========================================
echo.

echo Installing dependencies...
pip install -r requirements.txt >nul 2>&1
echo.

echo Cleaning old build artifacts...
if exist dist rd /s /q dist
if exist build rd /s /q build
del /F /Q *.spec 2>nul
del /F /Q OrderCollector*.exe 2>nul
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
echo.

echo Building single-file EXE with PyInstaller...
pyinstaller --onefile --windowed --name "OrderCollector" --icon=Logo.ico ^
    --distpath=dist ^
    --workpath=build ^
    --specpath=. ^
    --hidden-import=bs4 ^
    --hidden-import=keyring ^
    --hidden-import=keyring.backends ^
    --hidden-import=winreg ^
    --hidden-import=PySide6 ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=PySide6.QtGui ^
    --add-data=Logo.ico;. ^
    main.py

echo.
echo Cleaning up...
if exist build rd /s /q build
del /F /Q OrderCollector.spec 2>nul
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
echo.

echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Executable: dist\OrderCollector.exe
echo.
pause
