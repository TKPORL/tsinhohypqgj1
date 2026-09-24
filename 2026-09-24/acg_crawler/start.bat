@echo off
setlocal
cd /d "%~dp0"
title ACG Crawler

set "PYTHON_EXE=C:\Python314\python.exe"

if not exist "%PYTHON_EXE%" (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=py -3"
)

if not exist "%PYTHON_EXE%" (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)

echo ========================================
echo   ACG Resource Crawler
echo ========================================
echo.

if "%PYTHON_EXE%"=="" (
    echo [Error] Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

echo [Info] Using Python: %PYTHON_EXE%
%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo [Error] Python cannot start: %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo [Info] Created .env from .env.example.
    ) else (
        echo [Warn] .env was not found. ACGRX login may fail.
    )
)

rem ===== Check deps: skip pip install if importable =====
%PYTHON_EXE% -c "import flask, requests, bs4, lxml" >nul 2>&1
if errorlevel 1 (
    echo [1/3] Installing dependencies ^(first run only^)...
    %PYTHON_EXE% -m pip install -r requirements.txt -q
    if errorlevel 1 (
        echo [Error] pip install failed.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Dependencies OK, skip install.
)

echo [2/3] Opening browser...
start "" "http://127.0.0.1:5000"

echo [3/3] Starting server...
echo Close this window to stop the server.
echo.
%PYTHON_EXE% app.py

echo.
echo [Error] Server stopped.
pause
endlocal
