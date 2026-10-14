@echo off
setlocal
title PAMsim - installation
echo.
echo  ===============================================
echo   PAMsim - photon simulation for PAM: installer
echo  ===============================================
echo.
cd /d "%~dp0python"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo  Python was not found.
  echo  Install Python 3.9 or newer from https://www.python.org/downloads/
  echo  ^(tick "Add python.exe to PATH" during the installation^) and run this file again.
  echo.
  pause
  exit /b 1
)
echo  Using:
%PY% --version
echo.
echo  [1/3] Updating pip ...
%PY% -m pip install --upgrade pip || goto :error
echo.
echo  [2/3] Installing PAMsim and its libraries (numpy, numba, scipy, matplotlib, sv-ttk) ...
%PY% -m pip install -e ".[gui]" || goto :error
echo.
echo  [3/3] Creating the PAMsim shortcuts (Desktop and Start menu) ...
%PY% -m pamsim.shortcut || goto :error
echo.
echo  Done!  Start PAMsim with the icon on your Desktop or from the Start menu.
echo  (The very first simulation takes ~15 s longer because the code is compiled once.)
echo.
pause
exit /b 0

:error
echo.
echo  Installation failed - see the messages above.
echo.
pause
exit /b 1
