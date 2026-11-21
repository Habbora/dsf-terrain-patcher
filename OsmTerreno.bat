@echo off
cd /d "%~dp0"
if exist "%~dp0dist\OsmTerreno\OsmTerreno.exe" (
  start "" "%~dp0dist\OsmTerreno\OsmTerreno.exe"
  exit /b 0
)
if exist "%~dp0OsmTerreno.exe" (
  start "" "%~dp0OsmTerreno.exe"
  exit /b 0
)
where py >nul 2>&1
if errorlevel 1 (
  echo Nao achei o OsmTerreno.exe nem o Python.
  echo Rode Empacotar.bat para gerar o .exe, ou instale o Python 3.12.
  pause
  exit /b 1
)
start "" pyw -3.12 -m osmterreno
exit /b 0
