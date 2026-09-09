@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
uv run main.py >> logs\scheduler.log 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%DATE% %TIME%] MetaETL exit code %EXIT_CODE%>> logs\scheduler.log
exit /b %EXIT_CODE%
