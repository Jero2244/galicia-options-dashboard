@echo off
rem Builds from a clean venv so only requirements.txt packages are bundled (the Conda env pulls in GBs of unrelated libraries).
cd /d "%~dp0"
if not exist .buildenv\Scripts\python.exe (
    call "%USERPROFILE%\miniconda3\condabin\conda.bat" run --no-capture-output -n py4fi python -m venv .buildenv
    if errorlevel 1 goto :fail
)
.buildenv\Scripts\python -m pip install -q -r requirements.txt "pyinstaller>=6"
if errorlevel 1 goto :fail
.buildenv\Scripts\python -m PyInstaller GaliciaOptions.spec --noconfirm --clean
if errorlevel 1 goto :fail
if exist .env.example copy /y .env.example dist\GaliciaOptions\.env.example >nul
echo.
echo Built dist\GaliciaOptions\GaliciaOptions.exe
exit /b 0
:fail
echo Build failed.
pause
exit /b 1
