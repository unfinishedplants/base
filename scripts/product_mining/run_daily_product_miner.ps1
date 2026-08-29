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

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$RunsDir = Join-Path $RepoDir "workbench\product-leads\_runs"

if (-not (Test-Path $RunsDir)) {
    New-Item -ItemType Directory -Path $RunsDir -Force | Out-Null
}

$Timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$LogFile = Join-Path $RunsDir "product_miner_${Timestamp}.log"

Write-Output "Starting Product Lead Miner at $(Get-Date -Format o)" | Tee-Object -FilePath $LogFile
Write-Output "Repo Dir: $RepoDir" | Tee-Object -FilePath $LogFile -Append

$PythonCmd = "python"
$MinerScript = Join-Path $RepoDir "scripts\product_mining\mine_product_leads.py"

& $PythonCmd $MinerScript --lookback-hours $LookbackHours --max-candidates $MaxCandidates *>&1 | Tee-Object -FilePath $LogFile -Append
$ExitCode = $LASTEXITCODE

Write-Output "Finished Product Lead Miner with exit code $ExitCode at $(Get-Date -Format o)" | Tee-Object -FilePath $LogFile -Append

exit $ExitCode
