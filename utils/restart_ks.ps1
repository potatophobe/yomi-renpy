# Deploys the mod to Katawa Shoujo and restarts the game.
# Usage: utils\restart_ks.ps1 [-Root <Katawa Shoujo folder>]
# Without -Root, the game is looked up in the Steam libraries.
param([string]$Root = "")
$ErrorActionPreference = "Stop"

$GameFolder = "Katawa Shoujo"
$GameExe = "Katawa Shoujo.exe"
$GameProcess = "Katawa Shoujo"

# Steam's own folder is the first library; libraryfolders.vdf lists the others.
function Find-SteamGame([string]$folder) {
  $steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
  if (-not $steam) { throw "Steam not found; pass -Root <game folder>" }
  $libraries = @($steam)
  $config = Join-Path $steam "steamapps\libraryfolders.vdf"
  if (Test-Path $config) {
    $libraries += Select-String -Path $config -Pattern '"path"\s+"([^"]+)"' |
      ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\', '\' }
  }
  foreach ($library in $libraries) {
    $game = Join-Path $library "steamapps\common\$folder"
    if (Test-Path $game) { return $game }
  }
  throw "$folder not found in the Steam libraries; pass -Root <game folder>"
}

if (-not $Root) { $Root = Find-SteamGame $GameFolder }
& (Join-Path $PSScriptRoot "restart_game.ps1") -Root $Root -Exe (Join-Path $Root $GameExe) -Process $GameProcess
