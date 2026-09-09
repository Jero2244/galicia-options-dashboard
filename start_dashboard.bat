@echo off
cd /d "%~dp0"
call "%USERPROFILE%\miniconda3\condabin\conda.bat" run --no-capture-output -n py4fi python -m streamlit run app.py --server.headless false --server.address 127.0.0.1
if errorlevel 1 pause
