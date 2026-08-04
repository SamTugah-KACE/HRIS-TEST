param(
    [bool]$IncludePortal = $true,
    [bool]$WithGateway = $false
)

$ErrorActionPreference = "Stop"

function Write-Stage {
    param([string]$Message)
    Write-Host "[LOCAL-STACK] $Message" -ForegroundColor Cyan
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 180,
        [int]$IntervalSeconds = 2
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                return $true
            }
        } catch {
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }
    }
    return $false
}

function Start-ServiceWindow {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$Command
    )
    Write-Stage "Starting $Name in separate terminal..."
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$WorkingDirectory'; $Command"
    ) | Out-Null
}

function Resolve-AppDir {
    param(
        [string]$RepoRoot,
        [string]$LegacyName
    )
    $appsPath = switch ($LegacyName) {
        "portal" { Join-Path (Join-Path (Join-Path $RepoRoot "apps") "frontend") "portal" }
        "hris-core-api" { Join-Path (Join-Path (Join-Path $RepoRoot "apps") "backend") "hris-core-api" }
        "tenant-registry-service" { Join-Path (Join-Path (Join-Path $RepoRoot "apps") "backend") "tenant-registry-service" }
        default { Join-Path (Join-Path $RepoRoot "apps") $LegacyName }
    }
    $legacyPath = Join-Path $RepoRoot $LegacyName
    if (Test-Path $appsPath) {
        return $appsPath
    }
    return $legacyPath
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$tenantRegistryDir = Resolve-AppDir -RepoRoot $repoRoot -LegacyName "tenant-registry-service"
$hrisCoreDir = Resolve-AppDir -RepoRoot $repoRoot -LegacyName "hris-core-api"
$portalDir = Resolve-AppDir -RepoRoot $repoRoot -LegacyName "portal"
$gatewayDir = Join-Path (Join-Path (Join-Path $repoRoot "apps") "backend") "gateway"

foreach ($requiredPath in @($tenantRegistryDir, $hrisCoreDir, $portalDir)) {
    if (-not (Test-Path $requiredPath)) {
        throw "Required app directory is missing: $requiredPath"
    }
}
if ($WithGateway -and -not (Test-Path $gatewayDir)) {
    throw "Required app directory is missing: $gatewayDir"
}

Write-Stage "Step 1/4: Starting Tenant Registry service (bootstraps DB on first run)"
Start-ServiceWindow -Name "Tenant Registry" -WorkingDirectory $tenantRegistryDir -Command "python -m uvicorn app.main:app --reload --port 8001"
if (-not (Wait-HttpReady -Url "http://127.0.0.1:8001/health" -TimeoutSeconds 180)) {
    throw "Tenant Registry health check timed out. Check tenant-registry terminal logs."
}
Write-Stage "Tenant Registry is healthy."

Write-Stage "Step 2/4: Starting HRIS Core API"
Start-ServiceWindow -Name "HRIS Core API" -WorkingDirectory $hrisCoreDir -Command "python -m uvicorn app.main:app --reload --port 8000"
if (-not (Wait-HttpReady -Url "http://127.0.0.1:8000/health" -TimeoutSeconds 180)) {
    throw "HRIS Core API health check timed out. Check hris-core-api terminal logs."
}
Write-Stage "HRIS Core API is healthy."

if ($IncludePortal) {
    Write-Stage "Step 3/4: Starting Portal (Vite dev server)"
    Start-ServiceWindow -Name "Portal" -WorkingDirectory $portalDir -Command "npm run dev"
    if (-not (Wait-HttpReady -Url "http://127.0.0.1:5173" -TimeoutSeconds 180)) {
        throw "Portal health check timed out. Check portal terminal logs."
    }
    Write-Stage "Portal is reachable."
} else {
    Write-Stage "Step 3/4: Skipped portal startup (--IncludePortal:`$false)."
}

if ($WithGateway) {
    Write-Stage "Step 4/4: Starting GraphQL Gateway"
    Start-ServiceWindow -Name "GraphQL Gateway" -WorkingDirectory $gatewayDir -Command "python -m uvicorn app.main:app --reload --port 8010"
    if (-not (Wait-HttpReady -Url "http://127.0.0.1:8010/health" -TimeoutSeconds 180)) {
        throw "GraphQL Gateway health check timed out. Check gateway terminal logs."
    }
    Write-Stage "GraphQL Gateway is healthy."
}

Write-Stage "Local stack startup complete."
Write-Host ""
Write-Host "URLs:" -ForegroundColor Green
Write-Host "  Tenant Registry: http://127.0.0.1:8001/docs"
Write-Host "  HRIS Core API:   http://127.0.0.1:8000/docs"
if ($IncludePortal) {
    Write-Host "  Portal:          http://127.0.0.1:5173"
}
if ($WithGateway) {
    Write-Host "  GraphQL Gateway: http://127.0.0.1:8010/graphql"
}
