@echo off
REM Multimodal Medical AI Platform — double-click launcher.
REM Invokes start.ps1 with execution-policy bypass so users without a
REM signed-PowerShell setup can still run it.

setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%start.ps1"
endlocal

REM Pause so a double-clicked window stays open on errors.
pause
