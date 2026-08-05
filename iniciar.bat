@echo off
REM ============================================================
REM  GymManager Lite - Iniciar el programa
REM  Mantenga esta ventana abierta mientras use la aplicacion.
REM ============================================================
cd /d "%~dp0"
title GymManager Lite - servidor (no cerrar)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] El programa no esta instalado todavia.
    echo         Ejecute primero "instalar.bat".
    echo.
    pause
    exit /b 1
)

echo.
echo  Iniciando GymManager Lite...
echo  NO CIERRE esta ventana mientras use el programa.
echo  Para detenerlo: pulse Ctrl+C o cierre esta ventana.
echo.

".venv\Scripts\python.exe" run.py %*

REM  Si el servidor termina por un error, la ventana se queda abierta para
REM  poder leer el mensaje en vez de desaparecer al instante.
if errorlevel 1 (
    echo.
    echo  El servidor se detuvo con un error. Revise el mensaje de arriba.
    echo.
    pause
)
