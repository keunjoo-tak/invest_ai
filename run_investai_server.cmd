@echo off
cd /d D:\invest_ai
set PYTHONIOENCODING=utf-8
if "%SERVER_HOST%"=="" set SERVER_HOST=0.0.0.0
if "%SERVER_PORT%"=="" set SERVER_PORT=5000
D:\invest_ai\.venv\Scripts\python.exe -m uvicorn app.main:app --host %SERVER_HOST% --port %SERVER_PORT%
