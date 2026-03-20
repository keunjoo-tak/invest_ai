param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$envFile = Join-Path $root '.env'
$gcloud = 'D:\dev\tools\google-cloud-sdk\bin\gcloud.cmd'

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
    if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
      [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
  }
}

Import-DotEnv -Path $envFile

$required = @(
  'GCP_DEPLOY_PROJECT_ID',
  'GCP_DEPLOY_GOOGLE_APPLICATION_CREDENTIALS',
  'GEMINI_GOOGLE_APPLICATION_CREDENTIALS',
  'GEMINI_PROJECT_ID',
  'CLOUD_RUN_SERVICE_NAME',
  'CLOUD_RUN_REGION',
  'ARTIFACT_REGISTRY_REPOSITORY',
  'GEMINI_CREDENTIAL_SECRET_NAME'
)

$missing = @()
foreach ($name in $required) {
  if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
    $missing += $name
  }
}

$deployKey = [Environment]::GetEnvironmentVariable('GCP_DEPLOY_GOOGLE_APPLICATION_CREDENTIALS', 'Process')
$geminiKey = [Environment]::GetEnvironmentVariable('GEMINI_GOOGLE_APPLICATION_CREDENTIALS', 'Process')
$projectId = [Environment]::GetEnvironmentVariable('GCP_DEPLOY_PROJECT_ID', 'Process')
$serviceName = [Environment]::GetEnvironmentVariable('CLOUD_RUN_SERVICE_NAME', 'Process')
$region = [Environment]::GetEnvironmentVariable('CLOUD_RUN_REGION', 'Process')
$repository = [Environment]::GetEnvironmentVariable('ARTIFACT_REGISTRY_REPOSITORY', 'Process')
$runtimeSa = [Environment]::GetEnvironmentVariable('CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT', 'Process')
if (-not $runtimeSa -and $projectId) {
  $runtimeSa = "investai-cloudrun@$projectId.iam.gserviceaccount.com"
}

$result = [ordered]@{
  gcloud_exists = [bool](Test-Path $gcloud)
  deploy_credentials_exists = [bool]($deployKey -and (Test-Path $deployKey))
  gemini_credentials_exists = [bool]($geminiKey -and (Test-Path $geminiKey))
  project_id = $projectId
  service_name = $serviceName
  region = $region
  repository = $repository
  runtime_service_account = $runtimeSa
  missing = $missing
  ready = $false
}

if ($result.gcloud_exists -and $result.deploy_credentials_exists -and $result.gemini_credentials_exists -and $missing.Count -eq 0) {
  $result.ready = $true
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output ($result | ConvertTo-Json -Depth 5)
