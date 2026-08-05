@echo off
REM ============================================================
REM  GymManager Lite - Crear paquete para instalar en otro PC
REM  Genera un .zip con el programa, SIN los datos de este equipo.
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   GymManager Lite - Crear paquete de instalacion
echo ============================================================
echo.

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "HOY=%%i"
set "DESTINO=%CD%\GymManagerLite-!HOY!.zip"

if exist "!DESTINO!" del /q "!DESTINO!"

echo  Empaquetando...
echo.

REM  Se excluyen: .venv (se recrea al instalar), instance (datos de este equipo),
REM  __pycache__ y los propios paquetes generados antes.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$tmp = Join-Path $env:TEMP ('gml_' + [guid]::NewGuid().ToString('N'));" ^
  "New-Item -ItemType Directory -Path $tmp -Force | Out-Null;" ^
  "Get-ChildItem -Path '.' -Force | Where-Object {" ^
  "  $_.Name -notin @('.venv','instance','__pycache__','.git','.claude') -and $_.Extension -ne '.zip'" ^
  "} | ForEach-Object { Copy-Item $_.FullName -Destination $tmp -Recurse -Force };" ^
  "Get-ChildItem -Path $tmp -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force;" ^
  "Compress-Archive -Path (Join-Path $tmp '*') -DestinationPath '%DESTINO%' -Force;" ^
  "Remove-Item $tmp -Recurse -Force"

if not exist "!DESTINO!" (
    echo.
    echo  [ERROR] No se pudo crear el paquete.
    echo.
    pause
    exit /b 1
)

for %%A in ("!DESTINO!") do set "TAM=%%~zA"
set /a TAMKB=!TAM!/1024

echo  Paquete creado:
echo    !DESTINO!
echo    Tamano: !TAMKB! KB
echo.
echo  Para instalarlo en otro PC:
echo    1. Copie el .zip a ese equipo y descomprimalo.
echo    2. Ejecute "instalar.bat" dentro de la carpeta.
echo.
echo  NOTA: el paquete NO incluye sus datos (clientes, ventas, fotos).
echo        Para llevarlos, copie tambien la carpeta "instance"
echo        DESPUES de instalar en el equipo de destino.
echo.
pause
endlocal
exit /b 0
