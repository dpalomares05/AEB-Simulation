@echo off
rem Corre un ensayo de la carpeta ensayos\ sin abrir otras ventanas que CARLA.
rem El video, las graficas y el log quedan en Descargas\<fecha_hora>\.
rem Uso:  ensayo.bat                               lista los ensayos
rem       ensayo.bat ENCAP_CCRb_6_12
rem       ensayo.bat PROPIO_FRENA_18_3453 --entrada lider
setlocal
cd /d "%~dp0"
for /f "tokens=2 delims=:" %%a in ('chcp') do set "CP_ORIGINAL=%%a"
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "SALIDA=%TEMP%\aeb_sim_salida.txt"

if "%~1"=="" (
    echo Ensayos disponibles:
    for %%f in (ensayos\*.py) do echo    %%~nf
    echo.
    echo Uso: ensayo.bat NOMBRE [--entrada lider] [--sin-aeb]
    goto :fin_error
)
if not exist "ensayos\%~1.py" (
    echo No existe ensayos\%~1.py
    goto :fin_error
)

echo Iniciando simulación...

powershell -NoProfile -Command "function Up { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('localhost', 2000); $c.Close(); $true } catch { $false } }; if (-not (Up)) { Start-Process '..\CarlaUE4.exe' -ArgumentList '-windowed','-ResX=1280','-ResY=720','-quality-level=Low'; while (-not (Up)) { Start-Sleep 2 }; Start-Sleep 20 }"

"..\.venv\Scripts\python.exe" run_scenario.py %1 --descargas --graficas %2 %3 %4 %5 %6 %7 > "%SALIDA%" 2>&1
if errorlevel 1 (
    echo La simulación falló. Detalle:
    type "%SALIDA%"
    goto :fin_error
)
for /f "tokens=1,* delims= " %%a in ('findstr /b ">>>" "%SALIDA%"') do echo %%b
chcp %CP_ORIGINAL% >nul
exit /b 0

:fin_error
chcp %CP_ORIGINAL% >nul
exit /b 1
