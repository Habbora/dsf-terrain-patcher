@echo off
cd /d "%~dp0"
if exist "%~dp0dist\OsmTerreno\OsmTerreno.exe" (
  "%~dp0dist\OsmTerreno\OsmTerreno.exe" --compilar-todos
) else if exist "%~dp0OsmTerreno.exe" (
  "%~dp0OsmTerreno.exe" --compilar-todos
) else (
  py -3.12 -m osmterreno --compilar-todos
)
if errorlevel 1 pause
