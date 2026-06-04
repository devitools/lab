@echo off
REM Builda lab.exe (Windows).
REM Pré-requisito: Python 3.11+ no PATH.

setlocal
cd /d "%~dp0"

if not exist .venv (
    py -3 -m venv .venv
)
call .venv\Scripts\activate.bat

pip install --upgrade pip
pip install -r requirements.txt pyinstaller

pyinstaller --onefile --windowed --name lab --collect-all websockets --collect-all certifi app.py

echo.
echo Build finalizado: dist\lab.exe
endlocal
