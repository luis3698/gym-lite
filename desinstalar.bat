@echo off
REM ============================================================
REM  GymManager Lite - Desinstalar
REM  Quita el entorno y el acceso directo.
REM  Los DATOS (carpeta instance) se conservan salvo que lo pida.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   GymManager Lite - Desinstalacion
echo ============================================================
echo.
echo  Se quitaran:
echo    - El entorno con las dependencias (.venv)
echo    - El acceso directo del escritorio
echo.
echo  NO se tocaran sus datos (clientes, ventas, fotos)
echo  salvo que lo confirme al final.
echo.

choice /C SN /N /M "Continuar? (S/N): "
if errorlevel 2 goto :cancelado

echo.
echo  Quitando el entorno...
if exist ".venv" rmdir /s /q ".venv"

echo  Quitando el acceso directo...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Remove-Item ([Environment]::GetFolderPath('Desktop')+'\GymManager Lite.lnk') -ErrorAction SilentlyContinue" >nul 2>&1

echo.
echo  Hecho. La carpeta "instance" con sus datos sigue intacta.
echo.
echo  ATENCION: lo siguiente BORRA todos los clientes, ventas,
echo  inscripciones, usuarios y fotos. No se puede deshacer.
echo.
choice /C SN /N /M "Borrar TAMBIEN todos los datos? (S/N): "
if errorlevel 2 goto :fin
if exist "instance" rmdir /s /q "instance"
echo  Datos eliminados.

:fin
echo.
echo  Desinstalacion completada.
echo.
pause
endlocal
exit /b 0

:cancelado
echo.
echo  Cancelado. No se modifico nada.
echo.
pause
endlocal
exit /b 0
