<#
.SYNOPSIS
  Daily Product Lead Miner Runner for Windows Task Scheduler.
.DESCRIPTION
  Runs deterministic product lead extraction, saving execution logs to workbench/product-leads/_runs/.
#>

[CmdletBinding()]
param(
    [int]$LookbackHours = 24,
    [int]$MaxCandidates = 5
)

$ErrorActionPreference = "Continue"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = $Utf8NoBom
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$RunsDir = Join-Path $RepoDir "workbench\product-leads\_runs"

if (-not (Test-Path $RunsDir)) {
    New-Item -ItemType Directory -Path $RunsDir -Force | Out-Null
}

$Timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$LogFile = Join-Path $RunsDir "product_miner_${Timestamp}.log"
[System.IO.File]::WriteAllText($LogFile, "", $Utf8NoBom)

function Write-RunLog {
    param([AllowEmptyString()][string]$Message)
    Write-Output $Message
    [System.IO.File]::AppendAllText(
        $LogFile,
        $Message + [Environment]::NewLine,
        $Utf8NoBom
    )
}

Write-RunLog "Starting Product Lead Miner at $(Get-Date -Format o)"
Write-RunLog "Repo Dir: $RepoDir"

$PythonCmd = "python"
$MinerScript = Join-Path $RepoDir "scripts\product_mining\mine_product_leads.py"
$AuditScript = Join-Path $RepoDir "scripts\product_mining\audit_product_leads.py"

& $PythonCmd $MinerScript --lookback-hours $LookbackHours --max-candidates $MaxCandidates 2>&1 |
    ForEach-Object { Write-RunLog ([string]$_) }
$MinerExitCode = $LASTEXITCODE
$ExitCode = $MinerExitCode

if ($MinerExitCode -eq 0) {
    Write-RunLog "Starting Product Lead Audit with automatic downgrade"
    & $PythonCmd $AuditScript --auto-downgrade 2>&1 |
        ForEach-Object { Write-RunLog ([string]$_) }
    $ExitCode = $LASTEXITCODE
}

Write-RunLog "Finished Product Lead Pipeline with exit code $ExitCode at $(Get-Date -Format o)"

exit $ExitCode
