@echo off
setlocal
if exist "%~dp0Impressao OPs.exe" (
    start "" /D "%~dp0." "%~dp0Impressao OPs.exe"
    exit /b 0
)
if exist "%~dp0.venv-desktop\Scripts\pythonw.exe" (
    start "" /D "%~dp0." "%~dp0.venv-desktop\Scripts\pythonw.exe" "%~dp0impressao.py"
    exit /b 0
)
echo Ambiente desktop nao encontrado. Consulte DESKTOP.md.
pause
exit /b 1
