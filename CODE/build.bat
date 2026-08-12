@echo off
REM ============================================================
REM   JARVIS - Bootstrap Build Script
REM   ----------------------------------------------------------
REM   What this script does:
REM   1. Checks whether Python 3.11 exists. If not, downloads it.
REM   2. Creates a virtual environment for a clean build.
REM   3. Installs PyInstaller and all requirements.
REM   4. Builds a self-contained Jarvis.exe inside the dist\ folder
REM ============================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================
echo        JARVIS - Build Script
echo ============================================
echo.

REM === Settings ===
set PYTHON_VERSION=3.11.9
set PYTHON_INSTALLER=python-%PYTHON_VERSION%-amd64.exe
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%PYTHON_INSTALLER%
set REQUIRED_MAJOR=3
set REQUIRED_MINOR=11
set VENV_DIR=build_venv

REM ============================================================
REM   STEP 1: Check Python version
REM ============================================================
echo [1/5] Checking Python version...

set PYTHON_CMD=
set PYTHON_OK=0

for %%P in (py python python3) do (
    if !PYTHON_OK! == 0 (
        %%P --version >nul 2>&1
        if not errorlevel 1 (
            for /f "tokens=2" %%V in ('%%P --version 2^>^&1') do (
                set FOUND_VERSION=%%V
                for /f "tokens=1,2 delims=." %%a in ("%%V") do (
                    if %%a == !REQUIRED_MAJOR! if %%b == !REQUIRED_MINOR! (
                        set PYTHON_CMD=%%P
                        set PYTHON_OK=1
                    )
                )
            )
        )
    )
)

if !PYTHON_OK! == 1 (
    echo     [OK] Found Python !FOUND_VERSION! ^(command: !PYTHON_CMD!^)
    goto :PYTHON_READY
)

echo     [!] Python %REQUIRED_MAJOR%.%REQUIRED_MINOR% was not found.
echo.
echo [1b] Downloading Python %PYTHON_VERSION%...

if not exist "%PYTHON_INSTALLER%" (
    echo      Downloading from: %PYTHON_URL%
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'}"
    if errorlevel 1 (
        echo [X] Download failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo      [OK] Downloaded.
) else (
    echo      [OK] Installer already exists.
)

echo.
echo [1c] Installing Python %PYTHON_VERSION%...
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
if errorlevel 1 (
    echo [X] Python installation failed.
    pause
    exit /b 1
)

echo      [OK] Python was installed.
echo.
echo  [!] IMPORTANT: Close this window and run build.bat again.
echo.
pause
exit /b 0

:PYTHON_READY
echo.

REM ============================================================
REM   STEP 2: Check the entry-point script
REM ============================================================
if not exist "run_jarvis.py" (
    echo [X] run_jarvis.py was not found in this folder!
    echo     This file is required for the PyInstaller build.
    pause
    exit /b 1
)

REM ============================================================
REM   STEP 3: Create virtual environment
REM ============================================================
echo [2/5] Creating virtual environment...

REM ============================================================
REM   FIX (φορητότητα μεταξύ PC):
REM   Ένα Python venv ΔΕΝ είναι φορητό. Κρατάει μέσα του την
REM   απόλυτη διαδρομή του Python που το δημιούργησε. Αν το
REM   project αντιγραφεί σε άλλο PC (ή αλλάξει ο χρήστης), το
REM   παλιό build_venv δείχνει σε python.exe που δεν υπάρχει,
REM   και το pip αποτυγχάνει με "No Python at ...".
REM
REM   Γι' αυτό ΔΕΝ προσπερνάμε πια "τυφλά" ένα venv που υπάρχει.
REM   Αντί γι' αυτό ελέγχουμε αν είναι ΥΓΙΕΣ: τρέχουμε το
REM   python.exe του venv. Αν δεν δουλεύει, το σβήνουμε και το
REM   ξαναφτιάχνουμε αυτόματα από την αρχή.
REM ============================================================
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

set VENV_OK=0
if exist "%VENV_DIR%" (
    if exist "%VENV_PYTHON%" (
        "%VENV_PYTHON%" --version >nul 2>&1
        if not errorlevel 1 set VENV_OK=1
    )
)

if !VENV_OK! == 1 (
    echo     [OK] The venv already exists and is healthy ^(skipping^).
) else (
    if exist "%VENV_DIR%" (
        echo     [!] Existing venv is broken or from another PC.
        echo         Deleting and recreating it...
        rmdir /s /q "%VENV_DIR%"
    )
    !PYTHON_CMD! -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [X] Failed to create venv.
        pause
        exit /b 1
    )
    echo     [OK] Created.
)
echo.

REM ============================================================
REM   FIX: Instead of relying on `call activate.bat` + bare
REM   `python`, we call the venv's python.exe directly with its
REM   full path. With `setlocal enabledelayedexpansion` and the
REM   way this script runs, the PATH that activate.bat sets is
REM   not applied reliably to later bare `python` calls, so
REM   Windows could not find `python` and tried to open the
REM   Microsoft Store. Using the explicit path is 100% reliable
REM   because it does not depend on PATH at all.
REM ============================================================

if not exist "%VENV_PYTHON%" (
    echo [X] Could not find the venv python at "%VENV_PYTHON%".
    echo     The virtual environment may be corrupted.
    echo     Delete the "%VENV_DIR%" folder and run this script again.
    pause
    exit /b 1
)

REM ============================================================
REM   STEP 4: Install packages
REM ============================================================
echo [3/5] Installing packages...

"%VENV_PYTHON%" -m pip install --upgrade pip --quiet

if not exist "requirements.txt" (
    echo [X] requirements.txt was not found!
    pause
    exit /b 1
)

echo     Installing from requirements.txt...
"%VENV_PYTHON%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [X] Error while installing requirements.
    pause
    exit /b 1
)

echo     Installing PyInstaller...
"%VENV_PYTHON%" -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo [X] Error while installing PyInstaller.
    pause
    exit /b 1
)

echo     [OK] All packages were installed.
echo.

REM ============================================================
REM   STEP 5: Clean previous builds
REM ============================================================
echo [4/5] Cleaning old builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "Jarvis.spec" del "Jarvis.spec"
echo     [OK]
echo.

REM ============================================================
REM   STEP 6: Build the exe
REM ============================================================
echo [5/5] Creating Jarvis.exe...
echo     ^(this may take 2-5 minutes^)
echo.

set ICON_ARG=
if exist "jarvis.ico" set ICON_ARG=--icon "jarvis.ico"

set ENV_ARG=
if exist ".env" set ENV_ARG=--add-data ".env;."

REM IMPORTANT: We use run_jarvis.py as the entry point
REM instead of Jarvis\main.py directly, because otherwise relative imports break.
REM --collect-submodules Jarvis includes the entire package.
REM
REM FIX: PyInstaller is also invoked via the venv python so it
REM uses the packages we just installed into the venv, and we
REM now bundle pygame for audio playback (playsound removed).
"%VENV_PYTHON%" -m PyInstaller ^
    --name "Jarvis" ^
    --icon "jarvis.ico" ^
    --windowed ^
    --onefile ^
    %ENV_ARG% ^
    --collect-submodules Jarvis ^
    --collect-all edge_tts ^
    --collect-all speech_recognition ^
    --hidden-import "PySide6.QtCore" ^
    --hidden-import "PySide6.QtGui" ^
    --hidden-import "PySide6.QtWidgets" ^
    --hidden-import "pygame" ^
    run_jarvis.py

if errorlevel 1 (
    echo.
    echo [X] Failed to create exe.
    pause
    exit /b 1
)

echo.
echo ============================================
echo            BUILD COMPLETE!
echo ============================================
echo.
echo  The exe is located at: dist\Jarvis.exe
echo.
pause
endlocal