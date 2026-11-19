@echo off
rem 开发环境下启动（需先按 README 建好 .venv）
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
start "" ".venv\Scripts\pythonw.exe" -m cyct_report
