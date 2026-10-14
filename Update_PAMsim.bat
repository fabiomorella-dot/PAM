@echo off
setlocal
title PAMsim - update
cd /d "%~dp0"
echo  Downloading the latest version ...
git pull || goto :error
echo.
cd python
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY set "PY=python"
echo  Updating the installation ...
%PY% -m pip install -e ".[gui]" || goto :error
%PY% -m pamsim.shortcut >nul
echo.
echo  PAMsim is up to date.
pause
exit /b 0

:error
echo.
echo  Update failed - see the messages above.
pause
exit /b 1
