@echo off
rem Double-click helper: runs fix_integrity.ps1 with Administrator rights.
rem Fixes the Low mandatory-integrity label that the DSH/Codex sandbox leaves on
rem the workspace, which makes PyInstaller onefile exes fail with
rem "Could not create temporary directory!".
setlocal
set "PS1=%~dp0fix_integrity.ps1"

if not exist "%PS1%" (
    echo [ERROR] Not found: %PS1%
    pause
    exit /b 1
)

net session >nul 2>&1
if errorlevel 1 (
    echo Asking for Administrator rights, please confirm the UAC prompt...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-File',$env:PS1,'-Apply')"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Apply
echo.
pause
