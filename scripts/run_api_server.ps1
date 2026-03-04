$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
Set-Location "D:\invest_ai"
$env:DATABASE_URL = "postgresql+psycopg://postgres:0000@localhost:5432/postgres"

$logDir = Join-Path (Get-Location) "logs"
if (-not (Test-Path $logDir)) {
    New-Item -Path $logDir -ItemType Directory | Out-Null
}

$logFile = Join-Path $logDir "uvicorn.log"
$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$startedAt] starting uvicorn on 127.0.0.1:5000" | Tee-Object -FilePath $logFile -Append

$ErrorActionPreference = "Continue"
& C:\Python314\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5000 2>&1 |
    Tee-Object -FilePath $logFile -Append
