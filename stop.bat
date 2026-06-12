@echo off
REM Stop everything launched by start.bat.

setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%stop.ps1"
endlocal

pause
