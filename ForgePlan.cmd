@echo off
if exist "%~dp0app-next\ForgePlan.exe" (
    start "ForgePlan" "%~dp0app-next\ForgePlan.exe"
) else (
    start "ForgePlan" "%~dp0app\ForgePlan.exe"
)
