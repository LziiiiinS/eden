@echo off
cd /d "%~dp0"
docker compose stop
echo.
echo Eden parado. Para ligar de novo, use o iniciar-eden.
pause
