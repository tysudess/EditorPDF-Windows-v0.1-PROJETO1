@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   EDITOR DE PDF v0.2.1 - BUILD WINDOWS
echo ========================================

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "Editor-de-PDF" ^
  --icon "assets\editor_pdf_icon.ico" ^
  --add-data "assets\capa_padrao.png;assets" ^
  --add-data "assets\editor_pdf_icon.png;assets" ^
  --collect-all PySide6 ^
  main_v021.py

if errorlevel 1 (
  echo.
  echo ERRO NO BUILD.
  pause
  exit /b 1
)

echo.
echo PRONTO: dist\Editor-de-PDF.exe
pause
