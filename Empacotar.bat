@echo off
cd /d "%~dp0"
echo Instalando PyInstaller...
py -3.12 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Falha ao instalar dependencias.
  pause
  exit /b 1
)
echo.
echo Gerando OsmTerreno.exe ...
py -3.12 -m PyInstaller --noconfirm --clean OsmTerreno.spec
if errorlevel 1 (
  echo Falha no PyInstaller.
  pause
  exit /b 1
)
echo.
echo Pronto: dist\OsmTerreno\OsmTerreno.exe
echo Distribua a pasta inteira dist\OsmTerreno\
pause
