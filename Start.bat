@echo off
setlocal enabledelayedexpansion
title AnimeAIDub - Starting...
echo ============================================
echo   AnimeAIDub - Universal Media Dubbing Engine
echo ============================================
echo.

:: Set working directory to script location
cd /d "%~dp0"

:: ---- Check Python ----
where python >nul 2>&1
if %errorlevel% neq 0 (
    if exist "%ProgramFiles%\Python311\python.exe" (
        set "PYTHON=%ProgramFiles%\Python311\python.exe"
    ) else if exist "%ProgramFiles%\Python312\python.exe" (
        set "PYTHON=%ProgramFiles%\Python312\python.exe"
    ) else if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set "PYTHON=%LocalAppData%\Programs\Python\Python311\python.exe"
    ) else if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
        set "PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
    ) else (
        echo [SETUP] Python not found. Downloading...
        powershell -Command "Start-BitsTransfer -Source 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -Destination '%TEMP%\python-installer.exe'"
        if not exist "%TEMP%\python-installer.exe" (
            echo [ERROR] Failed to download Python. Please install Python 3.11+ manually.
            pause
            exit /b 1
        )
        echo [SETUP] Installing Python silently...
        "%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
        del "%TEMP%\python-installer.exe"
        set "PYTHON=%ProgramFiles%\Python311\python.exe"
    )
) else (
    set "PYTHON=python"
)

echo [OK] Python: Found
"!PYTHON!" --version

:: ---- Check FFmpeg ----
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    if exist "%~dp0ffmpeg\ffmpeg.exe" (
        set "PATH=%~dp0ffmpeg;%PATH%"
    ) else (
        echo [SETUP] FFmpeg not found. Downloading...
        mkdir "%~dp0ffmpeg" 2>nul
        powershell -Command "Start-BitsTransfer -Source 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -Destination '%TEMP%\ffmpeg.zip'"
        if not exist "%TEMP%\ffmpeg.zip" (
            echo [ERROR] Failed to download FFmpeg. Please install FFmpeg manually.
            pause
            exit /b 1
        )
        echo [SETUP] Extracting FFmpeg...
        powershell -Command "Expand-Archive -Path '%TEMP%\ffmpeg.zip' -DestinationPath '%TEMP%\ffmpeg-extract' -Force"
        for /d %%D in ("%TEMP%\ffmpeg-extract\ffmpeg-*") do (
            copy "%%D\bin\ffmpeg.exe" "%~dp0ffmpeg\" >nul
            copy "%%D\bin\ffprobe.exe" "%~dp0ffmpeg\" >nul
        )
        rmdir /s /q "%TEMP%\ffmpeg-extract" 2>nul
        del "%TEMP%\ffmpeg.zip" 2>nul
        set "PATH=%~dp0ffmpeg;%PATH%"
    )
)
echo [OK] FFmpeg: Found

:: ---- Create venv if needed ----
if not exist "%~dp0venv\Scripts\activate.bat" (
    echo [SETUP] Creating virtual environment...
    "!PYTHON!" -m venv "%~dp0venv"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)
echo [OK] Virtual environment ready

:: ---- Activate venv ----
call "%~dp0venv\Scripts\activate.bat"

:: ---- Install/update dependencies ----
if not exist "%~dp0venv\.installed" (
    echo [SETUP] Installing dependencies (this may take a while on first run)...
    pip install --upgrade pip >nul 2>&1
    pip install -r "%~dp0requirements.txt"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo done > "%~dp0venv\.installed"
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies already installed
)

:: ---- Launch app ----
echo.
echo ============================================
echo   Starting AnimeAIDub on http://localhost:29100
echo ============================================
echo   Press Ctrl+C to stop
echo.

:: Open browser after 2 second delay
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:29100"

:: Run the app
"!PYTHON!" -m src.main

pause
