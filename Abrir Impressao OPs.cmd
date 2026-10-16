@echo off
setlocal
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" /D "%~dp0." "%~dp0.venv\Scripts\pythonw.exe" "%~dp0impressao.py"
    exit /b 0
)
if exist "%~dp0venv32\Scripts\pythonw.exe" (
    start "" /D "%~dp0." "%~dp0venv32\Scripts\pythonw.exe" "%~dp0impressao.py"
    exit /b 0
)
echo Ambiente Python nao encontrado. Consulte a instalacao no README.md.
pause
exit /b 1
