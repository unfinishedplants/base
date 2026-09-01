<#
.SYNOPSIS
  Daily Koneta Miner Runner for Windows Task Scheduler.
.DESCRIPTION
  Runs deterministic 3-way koneta extraction across Antigravity, Codex, and Claude Code,
  saving execution logs to workbench/koneta-stock/_runs/.
#>

[CmdletBinding()]
param(
    [int]$LookbackHours = 24,
    [int]$MaxCards = 3
)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$RunsDir = Join-Path $RepoDir "workbench\koneta-stock\_runs"

if (-not (Test-Path $RunsDir)) {
    New-Item -ItemType Directory -Path $RunsDir -Force | Out-Null
}

$Timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$LogFile = Join-Path $RunsDir "koneta_miner_${Timestamp}.log"

Write-Output "Starting Koneta Miner at $(Get-Date -Format o)" | Tee-Object -FilePath $LogFile
Write-Output "Repo Dir: $RepoDir" | Tee-Object -FilePath $LogFile -Append

$PythonCmd = "python"
$MinerScript = Join-Path $RepoDir "scripts\koneta\mine_transcripts.py"

& $PythonCmd $MinerScript $LookbackHours $MaxCards *>&1 | Tee-Object -FilePath $LogFile -Append
$ExitCode = $LASTEXITCODE

Write-Output "Finished Koneta Miner with exit code $ExitCode at $(Get-Date -Format o)" | Tee-Object -FilePath $LogFile -Append

exit $ExitCode
