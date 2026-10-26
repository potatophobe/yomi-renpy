# Deploys the mod to a game and (re)starts it, waiting until the mod is loaded.
# Usage: utils\restart_game.ps1 -Root <dir containing game/> -Exe <exe> [-ExeArgs <args>] -Process <name>
param(
  [Parameter(Mandatory)] [string]$Root,
  [Parameter(Mandatory)] [string]$Exe,
  [string]$ExeArgs = "",
  [Parameter(Mandatory)] [string]$Process
)
$ErrorActionPreference = "Stop"

# Waiting: for the old game to exit, for the mod to load (checked every
# $PollMs, at most $LoadTimeoutSeconds), then for the first screen.
$ExitWaitMs = 800
$PollMs = 500
$LoadTimeoutSeconds = 60
$SettleSeconds = 4
$LogLinesShown = 8

$traceback = Join-Path $Root "traceback.txt"
$modLog = Join-Path $Root "game\yomi\yomi_log.txt"

# Git for Windows' bash runs deploy.sh. Found next to git, because a plain
# "bash" on Windows may be WSL's.
function Find-GitBash {
  $git = Get-Command git -ErrorAction SilentlyContinue
  if (-not $git) { throw "Git for Windows is needed to run deploy.sh (git not found in PATH)" }
  $directory = Split-Path $git.Source
  while ($directory) {
    $bash = Join-Path $directory "bin\bash.exe"
    if (Test-Path $bash) { return $bash }
    $directory = Split-Path $directory
  }
  throw "bash.exe not found in the Git installation at $(Split-Path $git.Source)"
}

Get-Process -Name $Process -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds $ExitWaitMs
& (Find-GitBash) (Join-Path $PSScriptRoot "deploy.sh") ($Root -replace '\\', '/') | Out-Null
Remove-Item $modLog -ErrorAction SilentlyContinue

$start = Get-Date
if ($ExeArgs) {
  Start-Process -FilePath $Exe -ArgumentList $ExeArgs -WorkingDirectory (Split-Path $Exe) | Out-Null
} else {
  Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe) | Out-Null
}

function Crashed { (Test-Path $traceback) -and ((Get-Item $traceback).LastWriteTime -gt $start) }

# Wait for the mod to report that it is installed (or for a crash).
$deadline = $start.AddSeconds($LoadTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds $PollMs
  if ((Test-Path $modLog) -or (Crashed)) { break }
}
Start-Sleep -Seconds $SettleSeconds
if (Crashed) { Get-Content $traceback }
if (Test-Path $modLog) { Get-Content $modLog -Encoding UTF8 | Select-Object -Last $LogLinesShown }
