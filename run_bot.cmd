@echo off
cd /d "%~dp0"
start "Telegram Bot" powershell -NoExit -Command "cd '%~dp0'; py -m app.main"
