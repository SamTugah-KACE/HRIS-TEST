param(
    [switch]$IncludePortal = $true
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

$repoRoot = Split-Path -Parent $PSScriptRoot
$tenantRegistryDir = Join-Path $repoRoot "tenant-registry-service"
$hrisCoreDir = Join-Path $repoRoot "hris-core-api"
$portalDir = Join-Path $repoRoot "portal"

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

Write-Stage "Step 4/4: Local stack startup complete."
Write-Host ""
Write-Host "URLs:" -ForegroundColor Green
Write-Host "  Tenant Registry: http://127.0.0.1:8001/docs"
Write-Host "  HRIS Core API:   http://127.0.0.1:8000/docs"
if ($IncludePortal) {
    Write-Host "  Portal:          http://127.0.0.1:5173"
}
