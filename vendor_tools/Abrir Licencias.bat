@echo off
rem Abre la administracion de licencias de GymManager Lite con doble clic.
rem
rem No hace falta saber de terminales ni de "python" contra "py": usa la ruta
rem absoluta de este mismo archivo (no depende de la carpeta desde la que se
rem abra) y "pyw", la version del lanzador de Python que no deja ninguna
rem ventana negra abierta detras de la interfaz grafica.

setlocal
set "SCRIPT_DIR=%~dp0"

where pyw >nul 2>nul
if errorlevel 1 (
    echo No se encontro Python en este equipo ^(el comando "pyw"^).
    echo.
    echo Instale Python desde https://www.python.org/downloads/ y marque la
    echo casilla "Add python.exe to PATH" durante la instalacion. Despues,
    echo vuelva a hacer doble clic en este archivo.
    echo.
    pause
    exit /b 1
)

start "" pyw "%SCRIPT_DIR%licensing_gui.py"
