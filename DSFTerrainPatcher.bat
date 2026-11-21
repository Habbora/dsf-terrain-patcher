@echo off
cd /d "%~dp0"
if exist "%~dp0dist\DSFTerrainPatcher\DSFTerrainPatcher.exe" (
  start "" "%~dp0dist\DSFTerrainPatcher\DSFTerrainPatcher.exe"
  exit /b 0
)
if exist "%~dp0DSFTerrainPatcher.exe" (
  start "" "%~dp0DSFTerrainPatcher.exe"
  exit /b 0
)
where py >nul 2>&1
if errorlevel 1 (
  echo Nao achei o DSFTerrainPatcher.exe nem o Python.
  echo Rode Empacotar.bat para gerar o .exe, ou instale o Python 3.12.
  pause
  exit /b 1
)
start "" pyw -3.12 -m osmterreno
exit /b 0
