@echo off
setlocal
set TASK_NAME=MetaETL Daily
set PROJECT_DIR=%~dp0
set RUNNER=%PROJECT_DIR%run_metaetl.cmd

schtasks /Create /TN "%TASK_NAME%" /TR "\"%RUNNER%\"" /SC DAILY /ST 02:00 /F
if errorlevel 1 (
  echo Failed to register the scheduled task.
  exit /b 1
)
echo Registered "%TASK_NAME%" to run daily at 02:00.
