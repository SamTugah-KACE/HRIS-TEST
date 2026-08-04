param(
    [switch]$KeycloakMode = $false,
    [switch]$Rebuild = $true,
    [string]$EnvFile = ".env.docker.development",
    [switch]$SkipEnvFile = $false,
    [int]$WaitTimeoutSeconds = 300,
    [switch]$SkipComposeWait = $false
)

$ErrorActionPreference = "Stop"

function Write-Stage {
    param([string]$Message)
    Write-Host "[DOCKER-STACK] $Message" -ForegroundColor Yellow
}

function Resolve-PythonCommand {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Exe = "python"
            Args = @()
        }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            Exe = "py"
            Args = @("-3")
        }
    }
    throw "Python was not found in PATH. Install Python 3 or run from an environment where python/py is available."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repoRoot "scripts/start_docker_stack.py"
if (-not (Test-Path $launcher)) {
    throw "Missing launcher: $launcher"
}

$pythonCmd = Resolve-PythonCommand
$pythonExe = [string]$pythonCmd.Exe
$pythonArgs = @($pythonCmd.Args)
$argsList = @($launcher)

if ($KeycloakMode) {
    $argsList += "--keycloak-mode"
}
if (-not $Rebuild) {
    $argsList += "--no-rebuild"
}
if ($SkipEnvFile) {
    $argsList += "--skip-env-file"
} else {
    $argsList += @("--env-file", $EnvFile)
}
if ($SkipComposeWait) {
    $argsList += "--skip-compose-wait"
}
$argsList += @("--wait-timeout-seconds", "$WaitTimeoutSeconds")

Write-Stage "Delegating startup to cross-platform launcher (start_docker_stack.py)..."
Set-Location $repoRoot
& $pythonExe @pythonArgs @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Cross-platform docker launcher failed with exit code $LASTEXITCODE."
}
