@echo off
cd /d "%~dp0"
if exist "%~dp0dist\DSFTerrainPatcher\DSFTerrainPatcher.exe" (
  "%~dp0dist\DSFTerrainPatcher\DSFTerrainPatcher.exe" --compilar-todos
) else if exist "%~dp0DSFTerrainPatcher.exe" (
  "%~dp0DSFTerrainPatcher.exe" --compilar-todos
) else (
  py -3.12 -m osmterreno --compilar-todos
)
if errorlevel 1 pause
