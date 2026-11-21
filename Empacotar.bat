@echo off
cd /d "%~dp0"
echo Instalando PyInstaller...
py -3.12 -m pip install -r requirements.txt pyinstaller==6.22.3
if errorlevel 1 (
  echo Falha ao instalar dependencias.
  pause
  exit /b 1
)
echo.
echo Gerando DSFTerrainPatcher.exe ...
py -3.12 -m PyInstaller --noconfirm --clean DSFTerrainPatcher.spec
if errorlevel 1 (
  echo Falha no PyInstaller.
  pause
  exit /b 1
)
echo.
echo Pronto: dist\DSFTerrainPatcher\DSFTerrainPatcher.exe
echo Distribua a pasta inteira dist\DSFTerrainPatcher\
pause
