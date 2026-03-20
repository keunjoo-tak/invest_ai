param(
  [switch]$SkipServicesEnable,
  [switch]$SkipSecretUpdate,
  [switch]$SkipBuild,
  [switch]$SkipDeploy
)

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

function Ensure-Repo {
  param([string]$ProjectId, [string]$Region, [string]$Repository)
  if (-not (Test-GCloudResource -Arguments @('artifacts', 'repositories', 'describe', $Repository, '--location', $Region, '--project', $ProjectId))) {
    Invoke-GCloud -Arguments @('artifacts', 'repositories', 'create', $Repository, '--repository-format=docker', '--location', $Region, '--project', $ProjectId, '--quiet')
  }
}

function Ensure-ServiceAccount {
  param([string]$ProjectId, [string]$Email)
  $name = $Email.Split('@')[0]
  if (-not (Test-GCloudResource -Arguments @('iam', 'service-accounts', 'describe', $Email, '--project', $ProjectId))) {
    Invoke-GCloud -Arguments @('iam', 'service-accounts', 'create', $name, '--display-name', 'InvestAI Cloud Run Runtime', '--project', $ProjectId, '--quiet')
  }
}

function Ensure-Secret {
  param([string]$ProjectId, [string]$SecretName, [string]$SecretFile)
  if (-not (Test-GCloudResource -Arguments @('secrets', 'describe', $SecretName, '--project', $ProjectId))) {
    Invoke-GCloud -Arguments @('secrets', 'create', $SecretName, '--replication-policy=automatic', '--project', $ProjectId, '--quiet')
  }
  Invoke-GCloud -Arguments @('secrets', 'versions', 'add', $SecretName, '--data-file', $SecretFile, '--project', $ProjectId, '--quiet')
}

function Ensure-ProjectBinding {
  param([string]$ProjectId, [string]$Member, [string]$Role)
  Invoke-GCloud -Arguments @('projects', 'add-iam-policy-binding', $ProjectId, '--member', $Member, '--role', $Role, '--quiet')
}

function Render-EnvYaml {
  param(
    [string]$SourceEnvPath,
    [string]$OutputPath,
    [string]$GeminiMountPath,
    [string]$DatabaseUrl,
    [bool]$SkipDatabaseUrl
  )
  $skipNames = @(
    'GOOGLE_APPLICATION_CREDENTIALS',
    'GEMINI_GOOGLE_APPLICATION_CREDENTIALS',
    'GCP_DEPLOY_PROJECT_ID',
    'GCP_DEPLOY_GOOGLE_APPLICATION_CREDENTIALS',
    'CLOUD_RUN_REGION',
    'CLOUD_RUN_SERVICE_NAME',
    'ARTIFACT_REGISTRY_REPOSITORY',
    'GEMINI_CREDENTIAL_SECRET_NAME',
    'CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT',
    'CLOUD_RUN_DATABASE_URL',
    'APP_ENV',
    'ENABLE_SCHEDULER',
    'DATABASE_URL',
    'SERVER_HOST',
    'SERVER_PORT',
    'DOWNLOADS_DIR',
    'SCHEDULER_SHARED_SECRET',
    'SCHEDULER_SHARED_SECRET_NAME',
    'CLOUD_SQL_CONNECTION_NAME',
    'CLOUD_SQL_DATABASE_URL_SECRET_NAME',
    'CLOUD_SQL_DB_PASSWORD_SECRET_NAME',
    'CLOUD_SQL_DATABASE_PASSWORD',
    'CLOUD_SQL_INSTANCE_NAME',
    'CLOUD_SQL_REGION',
    'CLOUD_SQL_DATABASE_NAME',
    'CLOUD_SQL_DATABASE_USER',
    'CLOUD_SQL_TIER',
    'CLOUD_SQL_DATABASE_VERSION',
    'CLOUD_SCHEDULER_REGION',
    'CLOUD_SCHEDULER_TIME_ZONE'
  )
  $lines = New-Object System.Collections.Generic.List[string]
  foreach ($rawLine in Get-Content $SourceEnvPath -Encoding UTF8) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#')) { continue }
    $index = $line.IndexOf('=')
    if ($index -lt 1) { continue }
    $name = $line.Substring(0, $index).Trim()
    $value = $line.Substring($index + 1).Trim()
    if ($skipNames -contains $name) { continue }
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    $escaped = $value.Replace("'", "''")
    $lines.Add("${name}: '$escaped'")
  }
  $lines.Add("SERVER_HOST: '0.0.0.0'")
  $lines.Add("SERVER_PORT: '8080'")
  $lines.Add("APP_ENV: 'cloudrun'")
  $lines.Add("ENABLE_SCHEDULER: 'false'")
  $lines.Add("DOWNLOADS_DIR: '/tmp/downloads'")
  if (-not $SkipDatabaseUrl) {
    $lines.Add("DATABASE_URL: '$($DatabaseUrl.Replace("'", "''"))'")
  }
  $lines.Add("GEMINI_GOOGLE_APPLICATION_CREDENTIALS: '$GeminiMountPath'")
  [System.IO.File]::WriteAllLines($OutputPath, $lines, [System.Text.UTF8Encoding]::new($false))
}

Import-DotEnv -Path $envFile

$projectId = Require-Value -Name 'GCP_DEPLOY_PROJECT_ID'
$deployCred = Require-Value -Name 'GCP_DEPLOY_GOOGLE_APPLICATION_CREDENTIALS'
$geminiCred = Require-Value -Name 'GEMINI_GOOGLE_APPLICATION_CREDENTIALS'
$serviceName = Require-Value -Name 'CLOUD_RUN_SERVICE_NAME'
$region = Require-Value -Name 'CLOUD_RUN_REGION'
$repository = Require-Value -Name 'ARTIFACT_REGISTRY_REPOSITORY'
$secretName = Require-Value -Name 'GEMINI_CREDENTIAL_SECRET_NAME'
$runtimeServiceAccount = Get-ValueOrDefault -Name 'CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT' -DefaultValue "investai-cloudrun@$projectId.iam.gserviceaccount.com"
$schedulerSecretName = [Environment]::GetEnvironmentVariable('SCHEDULER_SHARED_SECRET_NAME', 'Process')
$cloudSqlConnectionName = [Environment]::GetEnvironmentVariable('CLOUD_SQL_CONNECTION_NAME', 'Process')
$cloudSqlDatabaseUrlSecretName = [Environment]::GetEnvironmentVariable('CLOUD_SQL_DATABASE_URL_SECRET_NAME', 'Process')

if (-not (Test-Path $gcloud)) { throw "gcloud not found: $gcloud" }
if (-not (Test-Path $deployCred)) { throw "deployment credential file not found: $deployCred" }
if (-not (Test-Path $geminiCred)) { throw "Gemini credential file not found: $geminiCred" }

$env:GOOGLE_APPLICATION_CREDENTIALS = $deployCred
Invoke-GCloud -Arguments @('auth', 'activate-service-account', '--key-file', $deployCred, '--quiet')

if (-not $SkipServicesEnable) {
  Invoke-GCloud -Arguments @(
    'services', 'enable',
    'run.googleapis.com',
    'cloudbuild.googleapis.com',
    'artifactregistry.googleapis.com',
    'secretmanager.googleapis.com',
    'iam.googleapis.com',
    'cloudresourcemanager.googleapis.com',
    '--project', $projectId,
    '--quiet'
  )
  Start-Sleep -Seconds 10
}

Ensure-Repo -ProjectId $projectId -Region $region -Repository $repository
Ensure-ServiceAccount -ProjectId $projectId -Email $runtimeServiceAccount
Ensure-ProjectBinding -ProjectId $projectId -Member "serviceAccount:$runtimeServiceAccount" -Role 'roles/secretmanager.secretAccessor'
if ($cloudSqlConnectionName) {
  Ensure-ProjectBinding -ProjectId $projectId -Member "serviceAccount:$runtimeServiceAccount" -Role 'roles/cloudsql.client'
}

if (-not $SkipSecretUpdate) {
  Ensure-Secret -ProjectId $projectId -SecretName $secretName -SecretFile $geminiCred
}

$image = "${region}-docker.pkg.dev/$projectId/$repository/${serviceName}:latest"
$databaseUrl = [Environment]::GetEnvironmentVariable('CLOUD_RUN_DATABASE_URL', 'Process')
$useDatabaseSecret = [bool]$cloudSqlDatabaseUrlSecretName
if (-not $databaseUrl -and -not $useDatabaseSecret) {
  $databaseUrl = 'sqlite+pysqlite:////tmp/investai.db'
}
$geminiMountPath = '/var/secrets/gemini/adc.json'
$tempEnvFile = Join-Path ([System.IO.Path]::GetTempPath()) "investai-cloudrun-env-$([Guid]::NewGuid().ToString('N')).yaml"
Render-EnvYaml -SourceEnvPath $envFile -OutputPath $tempEnvFile -GeminiMountPath $geminiMountPath -DatabaseUrl $databaseUrl -SkipDatabaseUrl:$useDatabaseSecret

try {
  if (-not $SkipBuild) {
    Invoke-GCloud -Arguments @('builds', 'submit', '--tag', $image, '--project', $projectId, '--quiet', $root)
  }

  if (-not $SkipDeploy) {
    $deployArgs = @(
      'run', 'deploy', $serviceName,
      '--image', $image,
      '--region', $region,
      '--project', $projectId,
      '--platform', 'managed',
      '--allow-unauthenticated',
      '--port', '8080',
      '--memory', '2Gi',
      '--cpu', '2',
      '--timeout', '900',
      '--concurrency', '8',
      '--max-instances', '3',
      '--service-account', $runtimeServiceAccount,
      '--env-vars-file', $tempEnvFile,
      '--update-secrets', "/var/secrets/gemini/adc.json=${secretName}:latest",
      '--quiet'
    )

    if ($schedulerSecretName) {
      $deployArgs += @('--update-secrets', "SCHEDULER_SHARED_SECRET=${schedulerSecretName}:latest")
    }
    if ($cloudSqlDatabaseUrlSecretName) {
      $deployArgs += @('--update-secrets', "DATABASE_URL=${cloudSqlDatabaseUrlSecretName}:latest")
    }
    if ($cloudSqlConnectionName) {
      $deployArgs += @('--add-cloudsql-instances', $cloudSqlConnectionName)
    }

    Invoke-GCloud -Arguments $deployArgs
  }
} finally {
  Remove-Item $tempEnvFile -Force -ErrorAction SilentlyContinue
}

$url = & $gcloud run services describe $serviceName --region $region --project $projectId --format 'value(status.url)'
$result = [ordered]@{
  project_id = $projectId
  service_name = $serviceName
  region = $region
  image = $image
  runtime_service_account = $runtimeServiceAccount
  url = ($url | Out-String).Trim()
  database_url = if ($useDatabaseSecret) { "secret:$cloudSqlDatabaseUrlSecretName" } else { $databaseUrl }
  gemini_secret_name = $secretName
  scheduler_secret_name = $schedulerSecretName
  cloud_sql_connection_name = $cloudSqlConnectionName
}
$logsDir = Join-Path $root 'logs'
if (-not (Test-Path $logsDir)) {
  New-Item -ItemType Directory -Path $logsDir | Out-Null
}
$json = $result | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText((Join-Path $logsDir 'cloud_run_deploy_latest.json'), $json, [System.Text.UTF8Encoding]::new($false))
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output $json
