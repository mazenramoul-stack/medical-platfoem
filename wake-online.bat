@echo off
REM ==========================================================================
REM  One-click "wake up the online demo" launcher (Windows).
REM
REM  The website (Vercel) is always on, but the AI backend (Hugging Face Space)
REM  goes to sleep after ~48h with no visitors. This script pings the backend
REM  until it is fully awake, then opens your website in the browser.
REM
REM  Just double-click this file before a demo. First wake-up can take ~60s.
REM ==========================================================================
setlocal EnableDelayedExpansion

set "BACKEND=https://ma-zen-3-backend.hf.space/api/health/"
set "SITE=https://medical-platfoem.vercel.app/"
set "SPACE=https://huggingface.co/spaces/ma-zen-3/backend"
set "MAXTRIES=30"

echo.
echo  ===========================================================
echo    Waking up your online medical platform...
echo  ===========================================================
echo.
echo    Backend : %BACKEND%
echo    Website : %SITE%
echo.
echo    If it was asleep this can take up to a minute. Please wait.
echo.

set /a tries=0
:loop
set /a tries+=1
set "CODE=000"
for /f %%S in ('curl -s -o nul -w "%%{http_code}" -m 90 "%BACKEND%" 2^>nul') do set "CODE=%%S"
if "!CODE!"=="200" goto ready
echo    [try !tries!/%MAXTRIES%] still waking (status !CODE!) ... waiting 5s
if !tries! GEQ %MAXTRIES% goto giveup
timeout /t 5 /nobreak >nul
goto loop

:ready
echo.
echo    Backend is AWAKE (status 200). Opening your website...
start "" "%SITE%"
echo.
echo    All set. You can close this window.
echo.
pause
exit /b 0

:giveup
echo.
echo    The backend did not come up after %MAXTRIES% tries.
echo    Check the Space logs here:
echo        %SPACE%
echo    Opening the website anyway...
start "" "%SITE%"
echo.
pause
exit /b 1
