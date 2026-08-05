@echo off
REM ============================================================
REM  GymManager Lite - Instalador para Windows
REM  Haga doble clic en este archivo para instalar.
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   GymManager Lite - Instalacion
echo ============================================================
echo.

REM --- 1. Buscar Python -------------------------------------------------
REM  Se prueba primero el lanzador "py" (el que instala python.org) y luego
REM  "python", porque en muchos equipos solo uno de los dos esta en el PATH.
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo [ERROR] No se encontro Python en este equipo.
    echo.
    echo   1. Descarguelo de https://www.python.org/downloads/
    echo   2. Durante la instalacion MARQUE la casilla "Add Python to PATH".
    echo   3. Vuelva a ejecutar este instalador.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo [1/5] Python detectado: !PYVER!

REM  Flask 3 necesita Python 3.9 o superior.
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set "MAJOR=%%a"
    set "MINOR=%%b"
)
if !MAJOR! LSS 3 goto :versionvieja
if !MAJOR! EQU 3 if !MINOR! LSS 9 goto :versionvieja
goto :versionok

:versionvieja
echo.
echo [ERROR] Se necesita Python 3.9 o superior. Este equipo tiene !PYVER!.
echo         Actualicelo desde https://www.python.org/downloads/
echo.
pause
exit /b 1

:versionok

REM --- 2. Entorno virtual ----------------------------------------------
REM  Las dependencias se instalan en una carpeta .venv propia del proyecto,
REM  para no tocar el Python del sistema ni chocar con otros programas.
echo [2/5] Preparando el entorno aislado (.venv)...
if exist ".venv\Scripts\python.exe" (
    echo       Ya existia, se reutiliza.
) else (
    %PY% -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo crear el entorno virtual.
        echo         Compruebe que Python esta bien instalado.
        echo.
        pause
        exit /b 1
    )
)

set "VENVPY=%CD%\.venv\Scripts\python.exe"

REM --- 3. Dependencias --------------------------------------------------
echo [3/5] Instalando dependencias (puede tardar un minuto)...
"%VENVPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VENVPY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    echo         Revise su conexion a internet e intente de nuevo.
    echo.
    pause
    exit /b 1
)

REM --- 4. Base de datos -------------------------------------------------
echo [4/5] Creando la base de datos y los datos iniciales...
"%VENVPY%" -c "from app import create_app; create_app()"
if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo inicializar la base de datos.
    echo.
    pause
    exit /b 1
)

REM --- 5. Acceso directo en el escritorio -------------------------------
echo [5/5] Creando acceso directo en el escritorio...
set "PSLINK=$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\GymManager Lite.lnk');"
set "PSLINK=!PSLINK! $s.TargetPath='%CD%\iniciar.bat';"
set "PSLINK=!PSLINK! $s.WorkingDirectory='%CD%';"
set "PSLINK=!PSLINK! $s.IconLocation='%SystemRoot%\System32\shell32.dll,137';"
set "PSLINK=!PSLINK! $s.Description='Sistema de gestion de gimnasio';"
set "PSLINK=!PSLINK! $s.Save()"
powershell -NoProfile -ExecutionPolicy Bypass -Command "!PSLINK!" >nul 2>&1
if errorlevel 1 (
    echo       No se pudo crear el acceso directo, pero la instalacion es valida.
) else (
    echo       Listo: "GymManager Lite" en el escritorio.
)

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo   Para abrir el programa:
echo     - Doble clic en "GymManager Lite" del escritorio, o
echo     - Doble clic en "iniciar.bat" de esta carpeta.
echo.
echo   Usuario:    Admin
echo   Contrasena: Admin.123
echo.
echo   IMPORTANTE: cambie esa contrasena desde
echo   "Mi cuenta - Cambiar contrasena" la primera vez que entre.
echo.
echo ============================================================
echo.

choice /C SN /N /M "Abrir el programa ahora? (S/N): "
if errorlevel 2 goto :fin
if errorlevel 1 start "" "%CD%\iniciar.bat"

:fin
endlocal
exit /b 0
