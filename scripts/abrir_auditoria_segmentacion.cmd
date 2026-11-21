@echo off
setlocal
set "AUDIT_PROJECT=%~dp0.."
if not exist "%AUDIT_PROJECT%\.venv-training\Scripts\pythonw.exe" (
  echo No se encontro el Python del proyecto. Consulta la guia de auditoria.
  pause
  exit /b 1
)
start "" "%AUDIT_PROJECT%\.venv-training\Scripts\pythonw.exe" "%AUDIT_PROJECT%\scripts\annotation_audit_app.py" --root "%AUDIT_PROJECT%\outputs\blind_segmentation_50_20261113" --session principal
endlocal
