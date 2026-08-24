@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   EDITOR DE PDF - BUILD WINDOWS
echo ========================================

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "Editor-de-PDF" ^
  --add-data "assets\capa_padrao.png;assets" ^
  --collect-all PySide6 ^
  main.py

if errorlevel 1 (
  echo.
  echo ERRO NO BUILD.
  pause
  exit /b 1
)

echo.
echo PRONTO: dist\Editor-de-PDF.exe
pause
