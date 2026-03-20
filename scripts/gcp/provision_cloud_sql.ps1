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

function Get-ValueOrDefault {
  param([string]$Name, [string]$DefaultValue)
  $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
  if ($value) { return $value }
  return $DefaultValue
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

function New-RandomPassword {
  $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $bytes = New-Object byte[] 32
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
$instanceName = Get-ValueOrDefault -Name 'CLOUD_SQL_INSTANCE_NAME' -DefaultValue 'investai-pg'
$region = Get-ValueOrDefault -Name 'CLOUD_SQL_REGION' -DefaultValue 'asia-northeast3'
$databaseVersion = Get-ValueOrDefault -Name 'CLOUD_SQL_DATABASE_VERSION' -DefaultValue 'POSTGRES_16'
$tier = Get-ValueOrDefault -Name 'CLOUD_SQL_TIER' -DefaultValue 'db-custom-1-3840'
$edition = Get-ValueOrDefault -Name 'CLOUD_SQL_EDITION' -DefaultValue 'ENTERPRISE'
$databaseName = Get-ValueOrDefault -Name 'CLOUD_SQL_DATABASE_NAME' -DefaultValue 'investai'
$databaseUser = Get-ValueOrDefault -Name 'CLOUD_SQL_DATABASE_USER' -DefaultValue 'investai'
$passwordSecretName = Get-ValueOrDefault -Name 'CLOUD_SQL_DB_PASSWORD_SECRET_NAME' -DefaultValue 'investai-cloudsql-db-password'
$urlSecretName = Get-ValueOrDefault -Name 'CLOUD_SQL_DATABASE_URL_SECRET_NAME' -DefaultValue 'investai-cloudsql-database-url'
$password = [Environment]::GetEnvironmentVariable('CLOUD_SQL_DATABASE_PASSWORD', 'Process')

if (-not (Test-Path $gcloud)) { throw "gcloud not found: $gcloud" }
if (-not (Test-Path $deployCred)) { throw "deployment credential file not found: $deployCred" }

$env:GOOGLE_APPLICATION_CREDENTIALS = $deployCred
Invoke-GCloud -Arguments @('auth', 'activate-service-account', '--key-file', $deployCred, '--quiet')
Invoke-GCloud -Arguments @('services', 'enable', 'sqladmin.googleapis.com', 'secretmanager.googleapis.com', 'cloudresourcemanager.googleapis.com', '--project', $projectId, '--quiet')

if (-not (Test-GCloudResource -Arguments @('sql', 'instances', 'describe', $instanceName, '--project', $projectId))) {
  Invoke-GCloud -Arguments @(
    'sql', 'instances', 'create', $instanceName,
    '--project', $projectId,
    '--database-version', $databaseVersion,
    '--region', $region,
    '--tier', $tier,
    '--edition', $edition,
    '--storage-size', '20',
    '--storage-auto-increase',
    '--availability-type', 'zonal',
    '--backup-start-time', '03:00',
    '--quiet'
  )
}

$state = ''
for ($i = 0; $i -lt 120; $i++) {
  $state = (& $gcloud 'sql' 'instances' 'describe' $instanceName '--project' $projectId '--format' 'value(state)' | Out-String).Trim()
  if ($state -eq 'RUNNABLE') { break }
  Start-Sleep -Seconds 10
}
if ($state -ne 'RUNNABLE') {
  throw "Cloud SQL 인스턴스가 RUNNABLE 상태가 아닙니다: $state"
}

if (-not (Test-GCloudResource -Arguments @('sql', 'databases', 'describe', $databaseName, '--instance', $instanceName, '--project', $projectId))) {
  Invoke-GCloud -Arguments @('sql', 'databases', 'create', $databaseName, '--instance', $instanceName, '--project', $projectId, '--quiet')
}

if (-not $password) {
  if (Test-GCloudResource -Arguments @('secrets', 'versions', 'access', 'latest', '--secret', $passwordSecretName, '--project', $projectId)) {
    $password = (& $gcloud 'secrets' 'versions' 'access' 'latest' '--secret' $passwordSecretName '--project' $projectId | Out-String).Trim()
  } else {
    $password = New-RandomPassword
  }
}
Ensure-SecretValue -ProjectId $projectId -SecretName $passwordSecretName -SecretValue $password

$userList = (& $gcloud 'sql' 'users' 'list' '--instance' $instanceName '--project' $projectId '--format' 'value(name)' | Out-String).Split([Environment]::NewLine, [System.StringSplitOptions]::RemoveEmptyEntries)
$userExists = $userList -contains $databaseUser
if ($userExists) {
  Invoke-GCloud -Arguments @('sql', 'users', 'set-password', $databaseUser, '--instance', $instanceName, '--password', $password, '--project', $projectId, '--quiet')
} else {
  Invoke-GCloud -Arguments @('sql', 'users', 'create', $databaseUser, '--instance', $instanceName, '--password', $password, '--project', $projectId, '--quiet')
}

$connectionName = (& $gcloud 'sql' 'instances' 'describe' $instanceName '--project' $projectId '--format' 'value(connectionName)' | Out-String).Trim()
$encodedPassword = [System.Uri]::EscapeDataString($password)
$databaseUrl = "postgresql+psycopg://${databaseUser}:$encodedPassword@/${databaseName}?host=/cloudsql/$connectionName"
Ensure-SecretValue -ProjectId $projectId -SecretName $urlSecretName -SecretValue $databaseUrl

$logsDir = Join-Path $root 'logs'
if (-not (Test-Path $logsDir)) {
  New-Item -ItemType Directory -Path $logsDir | Out-Null
}
$result = [ordered]@{
  project_id = $projectId
  instance_name = $instanceName
  connection_name = $connectionName
  region = $region
  database_name = $databaseName
  database_user = $databaseUser
  tier = $tier
  edition = $edition
  password_secret_name = $passwordSecretName
  database_url_secret_name = $urlSecretName
  database_url = $databaseUrl
}
$json = $result | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText((Join-Path $logsDir 'cloud_sql_latest.json'), $json, [System.Text.UTF8Encoding]::new($false))
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output $json
