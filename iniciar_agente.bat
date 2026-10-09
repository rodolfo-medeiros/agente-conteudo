@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" goto rodar_venv
if exist "runtime\python.exe" goto rodar_runtime
echo Ambiente nao configurado. Rode setup.bat primeiro.
pause
exit /b 1

:rodar_venv
venv\Scripts\python.exe -m streamlit run app.py
pause
exit /b 0

:rodar_runtime
runtime\python.exe -m streamlit run app.py
pause