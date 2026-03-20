param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$envFile = Join-Path $root '.env'
$gcloud = 'D:\dev\tools\google-cloud-sdk\bin\gcloud.cmd'
$cloudSdkConfig = Join-Path $env:APPDATA 'gcloud'
if (-not (Test-Path $cloudSdkConfig)) {
  New-Item -ItemType Directory -Path $cloudSdkConfig | Out-Null
}
$env:CLOUDSDK_CONFIG = $cloudSdkConfig

function Import-DotEnv {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return }
  foreach ($rawLine in Get-Content $Path -Encoding UTF8) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#')) { continue }
    $index = $line.IndexOf('=')
    if ($index -lt 1) { continue }
    $name = $line.Substring(0, $index).Trim()
    $value = $line.Substring($index + 1).Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
  }
}

function Require-Value {
  param([string]$Name)
  $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
  if (-not $value) {
    throw "Missing required environment value: $Name"
  }
  return $value
}

function Invoke-GCloud {
  param([string[]]$Arguments)
  & $gcloud @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "gcloud command failed: $($Arguments -join ' ')"
  }
}

function Test-GCloudResource {
  param([string[]]$Arguments)
  $previousPreference = $global:ErrorActionPreference
  try {
    $global:ErrorActionPreference = 'Continue'
    & $gcloud @Arguments 1>$null 2>$null
    return ($LASTEXITCODE -eq 0)
  } finally {
    $global:ErrorActionPreference = $previousPreference
  }
}

function Ensure-SecretValue {
  param([string]$ProjectId, [string]$SecretName, [string]$SecretValue)
  if (-not (Test-GCloudResource -Arguments @('secrets', 'describe', $SecretName, '--project', $ProjectId))) {
    Invoke-GCloud -Arguments @('secrets', 'create', $SecretName, '--replication-policy=automatic', '--project', $ProjectId, '--quiet')
  }
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    [System.IO.File]::WriteAllText($tmp, $SecretValue, [System.Text.UTF8Encoding]::new($false))
    Invoke-GCloud -Arguments @('secrets', 'versions', 'add', $SecretName, '--data-file', $tmp, '--project', $ProjectId, '--quiet')
  } finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  }
}

function New-RandomSecret {
  $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $bytes = New-Object byte[] 48
  $rng.GetBytes($bytes)
  $builder = New-Object System.Text.StringBuilder
  foreach ($b in $bytes) {
    [void]$builder.Append($chars[$b % $chars.Length])
  }
  return $builder.ToString()
}

Import-DotEnv -Path $envFile

$projectId = Require-Value -Name 'GCP_DEPLOY_PROJECT_ID'
$deployCred = Require-Value -Name 'GCP_DEPLOY_GOOGLE_APPLICATION_CREDENTIALS'
$serviceName = Require-Value -Name 'CLOUD_RUN_SERVICE_NAME'
$serviceRegion = Require-Value -Name 'CLOUD_RUN_REGION'
$schedulerRegion = [Environment]::GetEnvironmentVariable('CLOUD_SCHEDULER_REGION', 'Process')
if (-not $schedulerRegion) { $schedulerRegion = $serviceRegion }
$timezone = [Environment]::GetEnvironmentVariable('CLOUD_SCHEDULER_TIME_ZONE', 'Process')
if (-not $timezone) { $timezone = 'Asia/Seoul' }
$secretName = [Environment]::GetEnvironmentVariable('SCHEDULER_SHARED_SECRET_NAME', 'Process')
if (-not $secretName) { $secretName = 'investai-scheduler-key' }
$secretValue = [Environment]::GetEnvironmentVariable('SCHEDULER_SHARED_SECRET', 'Process')

if (-not (Test-Path $gcloud)) { throw "gcloud not found: $gcloud" }
if (-not (Test-Path $deployCred)) { throw "deployment credential file not found: $deployCred" }

$env:GOOGLE_APPLICATION_CREDENTIALS = $deployCred
Invoke-GCloud -Arguments @('auth', 'activate-service-account', '--key-file', $deployCred, '--quiet')
Invoke-GCloud -Arguments @('services', 'enable', 'cloudscheduler.googleapis.com', 'secretmanager.googleapis.com', 'cloudresourcemanager.googleapis.com', '--project', $projectId, '--quiet')

if (-not $secretValue) {
  if (Test-GCloudResource -Arguments @('secrets', 'versions', 'access', 'latest', '--secret', $secretName, '--project', $projectId)) {
    $secretValue = (& $gcloud 'secrets' 'versions' 'access' 'latest' '--secret' $secretName '--project' $projectId | Out-String).Trim()
  } else {
    $secretValue = New-RandomSecret
  }
}
Ensure-SecretValue -ProjectId $projectId -SecretName $secretName -SecretValue $secretValue

$serviceUrl = (& $gcloud 'run' 'services' 'describe' $serviceName '--region' $serviceRegion '--project' $projectId '--format' 'value(status.url)' | Out-String).Trim()
if (-not $serviceUrl) {
  throw 'Cloud Run 서비스 URL을 확인하지 못했습니다.'
}

Push-Location $root
try {
  $jobJson = (& py (Join-Path $PSScriptRoot 'export_scheduler_jobs.py') | Out-String)
} finally {
  Pop-Location
}
$parsedJobs = $jobJson | ConvertFrom-Json
if ($parsedJobs -is [System.Array]) {
  $jobs = @($parsedJobs)
} else {
  $jobs = @($parsedJobs)
}

foreach ($job in $jobs) {
  $jobName = 'investai-' + $job.job_id.Replace('_', '-')
  $uri = $serviceUrl.TrimEnd('/') + $job.path
  $schedule = '{0} {1} * * *' -f $job.schedule_minute, $job.schedule_hour
  $body = ($job.body | ConvertTo-Json -Compress)
  $headers = "Content-Type=application/json,X-InvestAI-Scheduler-Key=$secretValue"

  if (Test-GCloudResource -Arguments @('scheduler', 'jobs', 'describe', $jobName, '--location', $schedulerRegion, '--project', $projectId)) {
    Invoke-GCloud -Arguments @(
      'scheduler', 'jobs', 'update', 'http', $jobName,
      '--location', $schedulerRegion,
      '--project', $projectId,
      '--schedule', $schedule,
      '--time-zone', $timezone,
      '--uri', $uri,
      '--http-method', 'POST',
      '--update-headers', $headers,
      '--message-body', $body,
      '--attempt-deadline', '1800s',
      '--quiet'
    )
  } else {
    Invoke-GCloud -Arguments @(
      'scheduler', 'jobs', 'create', 'http', $jobName,
      '--location', $schedulerRegion,
      '--project', $projectId,
      '--schedule', $schedule,
      '--time-zone', $timezone,
      '--uri', $uri,
      '--http-method', 'POST',
      '--headers', $headers,
      '--message-body', $body,
      '--attempt-deadline', '1800s',
      '--quiet'
    )
  }
}

$logsDir = Join-Path $root 'logs'
if (-not (Test-Path $logsDir)) {
  New-Item -ItemType Directory -Path $logsDir | Out-Null
}
$result = [ordered]@{
  project_id = $projectId
  scheduler_region = $schedulerRegion
  timezone = $timezone
  service_url = $serviceUrl
  secret_name = $secretName
  job_count = $jobs.Count
  jobs = @($jobs | ForEach-Object { $_.job_id })
}
$json = $result | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText((Join-Path $logsDir 'cloud_scheduler_latest.json'), $json, [System.Text.UTF8Encoding]::new($false))
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output $json
