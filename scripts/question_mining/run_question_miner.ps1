<# Manual runner for the beginner-question miner. No scheduled task is registered. #>

[CmdletBinding()]
param(
    [int]$LookbackHours = 168,
    [int]$MaxCandidates = 10,
    [int]$MinimumScore = 6,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$Miner = Join-Path $ScriptDir "mine_question_leads.py"

$Arguments = @(
    $Miner,
    "--lookback-hours", $LookbackHours,
    "--max-candidates", $MaxCandidates,
    "--minimum-score", $MinimumScore
)
if ($DryRun) {
    $Arguments += "--dry-run"
}

Push-Location $RepoDir
try {
    & python @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

