@echo off
title OrthoForge Patch Editor
cd /d "%~dp0"
echo Abrindo o editor...
echo Ctrl+C fecha o servidor.
echo.
where py >nul 2>&1 && (
  py -3 server.py
  goto :eof
)
python server.py
if errorlevel 1 pause
