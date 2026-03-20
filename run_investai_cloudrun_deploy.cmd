@echo off
cd /d D:\invest_ai
set PYTHONIOENCODING=utf-8
powershell -NoProfile -ExecutionPolicy Bypass -File D:\invest_ai\scripts\gcp\deploy_cloud_run.ps1
