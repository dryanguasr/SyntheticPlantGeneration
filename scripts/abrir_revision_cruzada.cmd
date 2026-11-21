@echo off
setlocal
if not defined UCHUVA_PYTHON if exist "%~dp0..\.venv-training\Scripts\pythonw.exe" set "UCHUVA_PYTHON=%~dp0..\.venv-training\Scripts\pythonw.exe"
if not defined UCHUVA_PYTHON if exist "%~dp0..\..\..\.venv-training\Scripts\pythonw.exe" set "UCHUVA_PYTHON=%~dp0..\..\..\.venv-training\Scripts\pythonw.exe"
if not defined UCHUVA_PYTHON set "UCHUVA_PYTHON=pythonw.exe"
start "" "%UCHUVA_PYTHON%" "%~dp0cross_review_app.py" %*
endlocal
